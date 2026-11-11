// Scoped native map patch: append one target to an existing packed layout.
// Preserve all original entries, other exports, imports and dependency data.
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TrainingDummy.DataBuilder;

internal static class LayoutPack
{
    const string Clone = "obl1350_Point_Icon_Bench_Boss";
    const string Arrival = "tgpMod_JunonColosseum_Arrival";
    const string ReturnGate = "tgpMod_JunonColosseum_ReturnGate";
    const int Stride = 318;
    static int I(byte[] b, int p) => BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(p));
    static ulong Q(byte[] b, int p) => BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(p));
    static void W(byte[] b, int p, int n) => BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p), n);
    static void WQ(byte[] b, int p, ulong n) => BinaryPrimitives.WriteUInt64LittleEndian(b.AsSpan(p), n);
    static void F(byte[] b, int p, float n) => BinaryPrimitives.WriteSingleLittleEndian(b.AsSpan(p), n);
    static void Require(bool value, string why) { if (!value) throw new InvalidDataException(why); }

    static List<string> Names(byte[] b)
    {
        var result = new List<string>();
        int p = I(b, 0x18), end = p + I(b, 0x1c);
        while (p < end)
        {
            int length = BinaryPrimitives.ReadUInt16BigEndian(b.AsSpan(p)); p += 2;
            bool wide = (length & 0x8000) != 0; length &= 0x7fff;
            int bytes = length * (wide ? 2 : 1);
            result.Add((wide ? Encoding.Unicode : Encoding.Latin1).GetString(b, p, bytes)); p += bytes;
        }
        Require(p == end, "Name batch boundary mismatch");
        return result;
    }

    static int Tag(byte[] b, List<string> names, string property, string type)
    {
        var pattern = new byte[16];
        W(pattern, 0, names.IndexOf(property)); W(pattern, 8, names.IndexOf(type));
        int found = -1;
        for (int i = 0; i <= b.Length - 16; i++)
            if (b.AsSpan(i, 16).SequenceEqual(pattern))
            { Require(found == -1, "Ambiguous property: " + property); found = i; }
        Require(found >= 0, "Missing property: " + property);
        return found;
    }

    public static void AddArrival(string input, string posePath, string output)
    {
        using var pose = JsonDocument.Parse(File.ReadAllText(posePath));
        var root = pose.RootElement;
        string Target = root.TryGetProperty("target", out var target) ? target.GetString()! : Arrival;
        Require(Target == Arrival || Target == ReturnGate, "Unowned target name");
        byte[] original = File.ReadAllBytes(input);
        var names = Names(original);
        Require(!names.Contains(Target), "Target already exists");
        int exports = I(original, 0x2c), bundles = I(original, 0x30);
        Require((bundles - exports) % 72 == 0, "Unexpected export map layout");
        int exportCount = (bundles - exports) / 72;
        int data = I(original, 0x34) + I(original, 0x38);
        int firstSize = checked((int)Q(original, exports + 8));
        int totalSize = Enumerable.Range(0, exportCount).Sum(i => checked((int)Q(original, exports + i * 72 + 8)));
        Require(data + totalSize == original.Length, "Unexpected export data boundaries");
        byte[] first = original.AsSpan(data, firstSize).ToArray();
        int tag = Tag(first, names, "Objects", "MapProperty");
        // MapProperty tag: Name, Type, Size, ArrayIndex, KeyType,
        // ValueType, HasPropertyGuid. Then removed keys and dense entries.
        Require(I(first, tag + 24) == names.IndexOf("NameProperty"), "Unexpected map key type");
        Require(I(first, tag + 32) == names.IndexOf("StructProperty"), "Unexpected map value type");
        Require(first[tag + 40] == 0, "Property GUID unsupported");
        int value = tag + 41, count = I(first, value + 4), mapSize = I(first, tag + 16);
        Require(I(first, value) == 0 && mapSize == 8 + count * Stride, "Unexpected packed point layout");
        var entries = Enumerable.Range(0, count).Select(i => first.AsSpan(value + 8 + i * Stride, Stride).ToArray()).ToList();
        Require(entries.All(e => I(e, 0) >= 0 && I(e, 0) < names.Count && I(e, 4) >= 0), "Invalid point key");
        Require(entries.Select(e => (I(e, 0), I(e, 4))).Distinct().Count() == count, "Duplicate point key");
        var matches = entries.Where(e => names[I(e, 0)] == Clone && I(e, 4) == 0).ToArray();
        Require(matches.Length == 1, "Expected exactly one benchmark target");
        byte[] added = (byte[])matches[0].Clone();
        W(added, 0, names.Count);
        var position = root.GetProperty("position");
        double x = position.GetProperty("x").GetDouble(), y = position.GetProperty("y").GetDouble(), z = position.GetProperty("z").GetDouble();
        double yaw = root.GetProperty("yaw").GetDouble();
        Require(double.IsFinite(x) && double.IsFinite(y) && double.IsFinite(z) && double.IsFinite(yaw), "Invalid pose");
        bool inFoyer = Math.Abs(x + 122488.4375) < 500 && Math.Abs(y - 32968.976562) < 500 && z > 6100 && z < 6400;
        bool atGate = Math.Abs(x + 63550.003906) < 500 && Math.Abs(y - 97098.429688) < 500 && z > 3200 && z < 3600;
        // Development only (owner 2026-11-10): a pose marked "development_arena" may stand on the
        // arena floor, so the owner can take a photo-mode screenshot there. Never in a release.
        bool devArena = root.TryGetProperty("development_arena", out var dev) && dev.ValueKind == JsonValueKind.True
                        && Math.Abs(x + 123780) < 2500 && Math.Abs(y - 28675) < 2500 && z > 6100 && z < 6400;
        Require(Target == Arrival ? (inFoyer || devArena) : atGate, "Pose outside owner-selected location");
        int translation = Tag(added, names, "Translation", "StructProperty");
        int rotation = Tag(added, names, "Rotation", "StructProperty");
        Require(I(added, translation + 16) == 12 && I(added, rotation + 16) == 16, "Unexpected transform layout");
        Require(I(added, translation + 24) == names.IndexOf("Vector") && I(added, rotation + 24) == names.IndexOf("Quat"), "Unexpected transform types");
        F(added, translation + 49, (float)x); F(added, translation + 53, (float)y); F(added, translation + 57, (float)z);
        double half = yaw * Math.PI / 360.0;
        F(added, rotation + 49, 0); F(added, rotation + 53, 0); F(added, rotation + 57, (float)Math.Sin(half)); F(added, rotation + 61, (float)Math.Cos(half));

        int insert = value + mapSize;
        using var payload = new MemoryStream();
        payload.Write(first.AsSpan(0, insert)); payload.Write(added); payload.Write(first.AsSpan(insert));
        byte[] revised = payload.ToArray();
        W(revised, tag + 16, mapSize + Stride); W(revised, value + 4, count + 1);

        // Append only our ASCII FName, preserving every original name/hash.
        byte[] name = Encoding.ASCII.GetBytes(Target);
        int oldNamesSize = I(original, 0x1c), oldHash = I(original, 0x20), oldHashSize = I(original, 0x24), oldImports = I(original, 0x28);
        int newNamesSize = oldNamesSize + 2 + name.Length, newHash = (64 + newNamesSize + 7) / 8 * 8;
        int newHashSize = oldHashSize + 8, newImports = newHash + newHashSize, shift = newImports - oldImports;
        byte[] header = original.AsSpan(0, 64).ToArray();
        W(header, 0x1c, newNamesSize); W(header, 0x20, newHash); W(header, 0x24, newHashSize);
        foreach (int p in new[] { 0x28, 0x2c, 0x30, 0x34 }) W(header, p, I(original, p) + shift);
        byte[] tables = original.AsSpan(oldImports, data - oldImports).ToArray();
        WQ(tables, exports - oldImports + 8, (ulong)(firstSize + Stride));
        for (int i = 1; i < exportCount; i++) WQ(tables, exports - oldImports + i * 72, Q(original, exports + i * 72) + Stride);
        using var stream = new MemoryStream();
        stream.Write(header); stream.Write(original.AsSpan(64, oldNamesSize));
        stream.WriteByte((byte)(name.Length >> 8)); stream.WriteByte((byte)name.Length); stream.Write(name);
        stream.Write(new byte[newHash - 64 - newNamesSize]); stream.Write(original.AsSpan(oldHash, oldHashSize));
        var hash = new byte[8]; WQ(hash, 0, CityHash.Hash64(Encoding.ASCII.GetBytes(Target.ToLowerInvariant()))); stream.Write(hash);
        stream.Write(tables); stream.Write(revised); stream.Write(original.AsSpan(data + firstSize));
        byte[] result = stream.ToArray();

        // Independent structural readback: originals and remaining exports exact.
        var newNames = Names(result);
        Require(newNames.Take(names.Count).SequenceEqual(names) && newNames.Last() == Target, "Name preservation failed");
        int newData = I(result, 0x34) + I(result, 0x38);
        int newValue = newData + value;
        Require(I(result, newValue + 4) == count + 1, "Point count readback failed");
        for (int i = 0; i < count; i++) Require(result.AsSpan(newValue + 8 + i * Stride, Stride).SequenceEqual(entries[i]), "Original point changed");
        Require(result.AsSpan(newValue + 8 + count * Stride, Stride).SequenceEqual(added), "New target readback failed");
        Require(result.AsSpan(newData + revised.Length).SequenceEqual(original.AsSpan(data + firstSize)), "Other export changed");
        Require(result.Length == original.Length + shift + Stride, "Package length mismatch");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllBytes(output, result);
        Console.WriteLine(JsonSerializer.Serialize(new { target = Target, original_points = count, appended_points = 1, x, y, z, yaw, original_sha256 = Convert.ToHexString(SHA256.HashData(original)), output_sha256 = Convert.ToHexString(SHA256.HashData(result)), native_acceptance = "pending" }));
    }
}
