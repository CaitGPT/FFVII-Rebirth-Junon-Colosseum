// Scoped prototype: clone the native prison battle-plan packages into owned
// Junon packages and translate their recorded world-space positions. Relative
// geometry, actor classes, cameras, imports and serialization order are retained.
// Two exact sources are accepted: the plan (territory actor, points, cameras)
// and its ServerBuild companion (the same-named territory server-build actor
// whose enemy spawn/summon lists are offsets from that actor, so it has no
// world-space positions to move).
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TrainingDummy.DataBuilder;

internal static class BattlePlanPack
{
    sealed record Profile(string SourceHash, string SourceLeaf, string TargetLeaf, int NameCount, int WorldVectors)
    {
        public string SourcePackage => "/Game/Level/Game/Field/2360-UNDRS/BattlePlan/" + SourceLeaf;
    }
    static readonly Profile[] Profiles =
    [
        new("7DF787BCE8DB6A3E1545ACDB714E68AD9A7DC9309B2EA5C6B7DC89A2DFC687E9", "2360-UNDRS_BattlePlan_Resident", "1300-JUNOA_BattlePlan_ModJunonColosseum", 159, 20),
        new("84FDF5244118A0ADA2E73F4FFD7B626FA2C5B91F41DE90EEF42758764147C258", "2360-UNDRS_BattlePlan_Resident_ServerBuild", "1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild", 72, 0),
    ];
    static int I(byte[] b, int p) => BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(p));
    static ulong Q(byte[] b, int p) => BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(p));
    static float F(byte[] b, int p) => BinaryPrimitives.ReadSingleLittleEndian(b.AsSpan(p));
    static void W(byte[] b, int p, int n) => BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p), n);
    static void WQ(byte[] b, int p, ulong n) => BinaryPrimitives.WriteUInt64LittleEndian(b.AsSpan(p), n);
    static void WF(byte[] b, int p, float n) => BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(p), n);
    static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }

    // UE4 legacy zen public exports carry a package-qualified global import
    // index, not UE5's package-relative public export hash. Renaming a package
    // must therefore re-key those exports as well as its FNames. Validate every
    // old identity against the native bytes before changing any of them.
    internal static int RelocateExportIdentities(byte[] original, byte[] relocated, List<string> oldNames, List<string> newNames, string sourcePackage, string targetPackage)
    {
        int exports=I(original,0x2c), end=I(original,0x30);
        Require((end-exports)%72==0, "Unexpected export-map size");
        int count=(end-exports)/72, changed=0;
        string PathFor(int index, List<string> names, string package, HashSet<int> parents)
        {
            Require(index>=0 && index<count && parents.Add(index), "Invalid/cyclic export outer");
            int at=exports+index*72, nameIndex=I(original,at+16), number=I(original,at+20);
            Require(nameIndex>=0 && nameIndex<names.Count && number>=0, "Unexpected mapped export name");
            string name=names[nameIndex]+(number>0 ? "_"+(number-1) : "");
            ulong outer=Q(original,at+24);
            string prefix;
            if(outer==ulong.MaxValue) prefix=package;
            else {
                Require((outer>>62)==0 && outer<(ulong)count, "External export outer is unsupported");
                prefix=PathFor((int)outer,names,package,parents);
            }
            parents.Remove(index);
            return prefix+"/"+name;
        }
        ulong Identity(string path) => (CityHash.Hash64(Encoding.Unicode.GetBytes(path.Replace(':','/').Replace('.','/').ToLowerInvariant())) & 0x3fffffffffffffffUL) | 0x8000000000000000UL;
        for(int index=0;index<count;index++)
        {
            int at=exports+index*72;
            ulong before=Q(original,at+56);
            if(before==0 || before==ulong.MaxValue) continue;
            string oldPath=PathFor(index,oldNames,sourcePackage,[]);
            Require(before==Identity(oldPath), "Native export identity mismatch: "+oldPath);
            ulong after=Identity(PathFor(index,newNames,targetPackage,[]));
            Require(before!=after, "Export identity did not change with owned package");
            WQ(relocated,at+56,after);changed++;
        }
        Require(changed>0, "No native public exports found");
        return changed;
    }

    public static void Clone(string input, string posePath, string output)
    {
        byte[] original = File.ReadAllBytes(input);
        string sourceHash = Convert.ToHexString(SHA256.HashData(original));
        Profile profile = Profiles.SingleOrDefault(x => x.SourceHash == sourceHash) ?? throw new InvalidDataException("Unexpected native battle-plan source; retain/version the original");
        string SourceLeaf = profile.SourceLeaf, SourcePackage = profile.SourcePackage, TargetLeaf = profile.TargetLeaf;
        using var pose = JsonDocument.Parse(File.ReadAllText(posePath));
        var center = pose.RootElement.GetProperty("centre");
        double tx = center.GetProperty("x").GetDouble(), ty = center.GetProperty("y").GetDouble(), tz = center.GetProperty("z").GetDouble();
        Require(Math.Abs(tx + 124000) < 300 && Math.Abs(ty - 28600) < 300 && tz >= 6150 && tz <= 6200, "Battle centre outside recorded Roche arena");
        const float sx = 59330, sy = -24290, sz = 298;
        float dx = (float)(tx - sx), dy = (float)(ty - sy), dz = (float)(tz - sz);
        string normalized = Path.GetFullPath(output).Replace('\\', '/');
        string region = new[] { "1300-JUNOA", "1350-JNONT" }.SingleOrDefault(r => normalized.EndsWith("/End/Content/Level/Game/Field/" + r + "/BattlePlan/" + TargetLeaf + ".umap", StringComparison.OrdinalIgnoreCase));
        Require(region != null, "Unowned battle-plan output path");
        string targetPackage = "/Game/Level/Game/Field/" + region + "/BattlePlan/" + TargetLeaf;

        var names = new List<string>();
        int p = I(original, 0x18), end = p + I(original, 0x1c);
        while (p < end)
        {
            int n = BinaryPrimitives.ReadUInt16BigEndian(original.AsSpan(p)); p += 2;
            bool wide = (n & 0x8000) != 0; n &= 0x7fff;
            int size = n * (wide ? 2 : 1);
            names.Add((wide ? Encoding.Unicode : Encoding.Latin1).GetString(original, p, size)); p += size;
        }
        Require(p == end && names.Count == profile.NameCount, "Native name batch changed");
        int packageIndex = names.IndexOf(SourcePackage), leafIndex = names.IndexOf(SourceLeaf);
        Require(packageIndex >= 0 && leafIndex >= 0 && !names.Contains(TargetLeaf), "Unexpected native package identity");
        int oldHash = I(original, 0x20), hashSize = I(original, 0x24), oldImports = I(original, 0x28);
        Require(hashSize == 8 + names.Count * 8, "Unexpected name hash batch");
        byte[] hashes = original.AsSpan(oldHash, hashSize).ToArray();
        foreach (int index in new[] { packageIndex, leafIndex })
            Require(Q(hashes, 8 + index * 8) == CityHash.Hash64(Encoding.ASCII.GetBytes(names[index].ToLowerInvariant())), "Native name hash algorithm mismatch");
        var oldNames=new List<string>(names);
        names[packageIndex] = targetPackage; names[leafIndex] = TargetLeaf;
        foreach (int index in new[] { packageIndex, leafIndex }) WQ(hashes, 8 + index * 8, CityHash.Hash64(Encoding.ASCII.GetBytes(names[index].ToLowerInvariant())));

        byte[] relocated = (byte[])original.Clone();
        int renamedExports=RelocateExportIdentities(original,relocated,oldNames,names,SourcePackage,targetPackage);
        int data = I(original, 0x34) + I(original, 0x38);
        var moved = new List<int>();
        // The plan source contains twenty world-space vectors in the native
        // arena bounds: ten packed points, root/camera/summon positions and
        // the territory bounds. The ServerBuild source contains none: its 7447
        // spawn/summon translations are offsets within +/-26 m. The remaining
        // geometry is relative. Binding each source hash and exact count
        // prevents applying this to another map.
        for (int at = data; at <= original.Length - 12; at++)
        {
            float x = F(original, at), y = F(original, at + 4), z = F(original, at + 8);
            if (!(x > 49373 && x < 69373 && y > -34289 && y < -14289 && z > -5000 && z < 10000)) continue;
            Require(moved.Count == 0 || at >= moved[^1] + 12, "Overlapping relocation candidates");
            moved.Add(at); WF(relocated, at, x + dx); WF(relocated, at + 4, y + dy); WF(relocated, at + 8, z + dz);
        }
        Require(moved.Count == profile.WorldVectors, "Native world-position set changed");
        var allowed = new bool[original.Length - data];
        foreach (int at in moved) Array.Fill(allowed, true, at - data, 12);
        for (int at = data; at < original.Length; at++) Require(allowed[at-data] || relocated[at] == original[at], "Unscoped payload edit");

        using var batch = new MemoryStream();
        // Preserve every original entry's encoding bytes except the two owned
        // replacements; do not normalize the native names or their hashes.
        p = I(original, 0x18);
        for (int index = 0; index < names.Count; index++)
        {
            int start = p, n = BinaryPrimitives.ReadUInt16BigEndian(original.AsSpan(p)); p += 2;
            int size = (n & 0x7fff) * ((n & 0x8000) != 0 ? 2 : 1); p += size;
            if (index != packageIndex && index != leafIndex) batch.Write(original.AsSpan(start, p-start));
            else
            {
                byte[] value = Encoding.ASCII.GetBytes(names[index]);
                Require(value.Length < 0x8000, "Package name too long");
                batch.WriteByte((byte)(value.Length >> 8)); batch.WriteByte((byte)value.Length); batch.Write(value);
            }
        }
        int newNamesSize = checked((int)batch.Length), newHash = (64 + newNamesSize + 7) / 8 * 8;
        int newImports = newHash + hashSize, shift = newImports - oldImports;
        byte[] header = original.AsSpan(0,64).ToArray();
        W(header,0x1c,newNamesSize); W(header,0x20,newHash);
        foreach(int offset in new[] {0x28,0x2c,0x30,0x34}) W(header,offset,I(original,offset)+shift);
        using var stream = new MemoryStream();
        stream.Write(header); stream.Write(batch.ToArray()); stream.Write(new byte[newHash-64-newNamesSize]); stream.Write(hashes);
        stream.Write(relocated.AsSpan(oldImports));
        byte[] result = stream.ToArray();
        Require(result.Length == original.Length + shift, "Package length mismatch");
        int newData = I(result,0x34)+I(result,0x38);
        Require(newData == data + shift && result.AsSpan(newData).SequenceEqual(relocated.AsSpan(data)), "Payload relocation readback failed");
        Require(result.AsSpan(newImports,newData-newImports).SequenceEqual(relocated.AsSpan(oldImports,data-oldImports)), "Unexpected import/export/bundle edit");
        foreach(int at in moved)
        {
            Require(Math.Abs(F(result,at+shift)-(F(original,at)+dx))<.02 && Math.Abs(F(result,at+shift+4)-(F(original,at+4)+dy))<.02 && Math.Abs(F(result,at+shift+8)-(F(original,at+8)+dz))<.02, "Vector readback failed");
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllBytes(output,result);
        Console.WriteLine(JsonSerializer.Serialize(new { target_package=targetPackage, relocated_public_exports=renamedExports, relocated_world_vectors=moved.Count, tx,ty,tz,dx,dy,dz, source_package=SourcePackage, source_sha256=sourceHash, output_sha256=Convert.ToHexString(SHA256.HashData(result)), native_acceptance="pending" }));
    }
}
