// The Junon colosseum menu backdrop (owner 2026-11-10: a blurred, vignetted
// screenshot of the arena). It clones one exact native texture, the Musclehead
// backdrop U_Com_GoldSaucerArena_Bg1 (1920x1920 BC7, one inline mip, one export,
// no package imports), renames the package and its object, re-keys the public
// export and swaps in our BC7 pixels of exactly the same size. Every other byte
// is kept: format, mip header, sizes and serialization order.
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TrainingDummy.DataBuilder;

internal static class TexturePack
{
    const string SourceHash = "3F96DE19E9FD5C6260FA97A871B5C3E6E80BE0BAAA89D5C584BAA42493B329A1";
    const string SourcePackage = "/Game/Menu/Billboard/Common/U_Com_GoldSaucerArena_Bg1", SourceLeaf = "U_Com_GoldSaucerArena_Bg1";
    const string TargetPackage = "/Game/Menu/Billboard/Common/U_Com_JunonArena_Bg1", TargetLeaf = "U_Com_JunonArena_Bg1";
    const int PixelBytes = 1920 * 1920; // BC7: one byte per pixel
    static int I(byte[] b, int p) => BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(p));
    static ulong Q(byte[] b, int p) => BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(p));
    static void W(byte[] b, int p, int n) => BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p), n);
    static void WQ(byte[] b, int p, ulong n) => BinaryPrimitives.WriteUInt64LittleEndian(b.AsSpan(p), n);
    static void Require(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }

    public static void Clone(string input, string pixelsPath, string output)
    {
        byte[] original = File.ReadAllBytes(input);
        Require(Convert.ToHexString(SHA256.HashData(original)) == SourceHash, "Unexpected native backdrop source");
        byte[] pixels = File.ReadAllBytes(pixelsPath);
        Require(pixels.Length == PixelBytes, "Backdrop pixels must be 1920x1920 BC7 (" + PixelBytes + " bytes)");
        string normalized = Path.GetFullPath(output).Replace('\\', '/');
        Require(normalized.EndsWith("/End/Content/Menu/Billboard/Common/" + TargetLeaf + ".uasset", StringComparison.Ordinal), "Unowned backdrop output path");

        // Name batch: rename only the package and its object.
        var names = new List<string>();
        int p = I(original, 0x18), end = p + I(original, 0x1c);
        while (p < end)
        {
            int n = BinaryPrimitives.ReadUInt16BigEndian(original.AsSpan(p)); p += 2;
            bool wide = (n & 0x8000) != 0; n &= 0x7fff;
            int size = n * (wide ? 2 : 1);
            names.Add((wide ? Encoding.Unicode : Encoding.Latin1).GetString(original, p, size)); p += size;
        }
        Require(p == end, "Native name batch changed");
        int packageIndex = names.IndexOf(SourcePackage), leafIndex = names.IndexOf(SourceLeaf);
        Require(packageIndex >= 0 && leafIndex >= 0 && !names.Contains(TargetLeaf), "Unexpected native package identity");
        int oldHash = I(original, 0x20), hashSize = I(original, 0x24), oldImports = I(original, 0x28);
        Require(hashSize == 8 + names.Count * 8, "Unexpected name hash batch");
        byte[] hashes = original.AsSpan(oldHash, hashSize).ToArray();
        foreach (int index in new[] { packageIndex, leafIndex })
            Require(Q(hashes, 8 + index * 8) == CityHash.Hash64(Encoding.ASCII.GetBytes(names[index].ToLowerInvariant())), "Native name hash algorithm mismatch");
        var oldNames = new List<string>(names);
        names[packageIndex] = TargetPackage; names[leafIndex] = TargetLeaf;
        foreach (int index in new[] { packageIndex, leafIndex }) WQ(hashes, 8 + index * 8, CityHash.Hash64(Encoding.ASCII.GetBytes(names[index].ToLowerInvariant())));

        byte[] relocated = (byte[])original.Clone();
        int renamed = BattlePlanPack.RelocateExportIdentities(original, relocated, oldNames, names, SourcePackage, TargetPackage);
        Require(renamed == 1, "Expected one public texture export");

        // The first (only) mip: bulk flags, element count, size on disk, offset, then the pixels.
        int data = I(original, 0x34) + I(original, 0x38), pixelsAt = -1;
        for (int at = data; at < data + 4096; at++)
            if (I(original, at + 4) == PixelBytes && I(original, at + 8) == PixelBytes) { pixelsAt = at + 20; break; }
        Require(pixelsAt > 0 && pixelsAt + PixelBytes + 12 <= original.Length, "Mip data not found");
        Require(I(original, pixelsAt + PixelBytes) == 1920 && I(original, pixelsAt + PixelBytes + 4) == 1920, "Unexpected mip size");
        Array.Copy(pixels, 0, relocated, pixelsAt, PixelBytes);

        using var batch = new MemoryStream();
        p = I(original, 0x18);
        for (int index = 0; index < names.Count; index++)
        {
            int start = p, n = BinaryPrimitives.ReadUInt16BigEndian(original.AsSpan(p)); p += 2;
            p += (n & 0x7fff) * ((n & 0x8000) != 0 ? 2 : 1);
            if (index != packageIndex && index != leafIndex) batch.Write(original.AsSpan(start, p - start));
            else
            {
                byte[] value = Encoding.ASCII.GetBytes(names[index]);
                batch.WriteByte((byte)(value.Length >> 8)); batch.WriteByte((byte)value.Length); batch.Write(value);
            }
        }
        int newNamesSize = checked((int)batch.Length), newHash = (64 + newNamesSize + 7) / 8 * 8;
        int newImports = newHash + hashSize, shift = newImports - oldImports;
        byte[] header = original.AsSpan(0, 64).ToArray();
        W(header, 0x1c, newNamesSize); W(header, 0x20, newHash);
        foreach (int offset in new[] { 0x28, 0x2c, 0x30, 0x34 }) W(header, offset, I(original, offset) + shift);
        using var stream = new MemoryStream();
        stream.Write(header); stream.Write(batch.ToArray()); stream.Write(new byte[newHash - 64 - newNamesSize]); stream.Write(hashes);
        stream.Write(relocated.AsSpan(oldImports));
        byte[] result = stream.ToArray();
        Require(result.Length == original.Length + shift, "Package length mismatch");
        Require(result.AsSpan(pixelsAt + shift, PixelBytes).SequenceEqual(pixels), "Pixel readback failed");
        int newData = I(result, 0x34) + I(result, 0x38);
        for (int at = data; at < original.Length; at++)
            Require((at >= pixelsAt && at < pixelsAt + PixelBytes) || result[at + shift] == original[at], "Unscoped payload edit");
        Require(newData == data + shift, "Export data moved unexpectedly");
        Directory.CreateDirectory(Path.GetDirectoryName(normalized)!);
        File.WriteAllBytes(output, result);
        Console.WriteLine(JsonSerializer.Serialize(new { target_package = TargetPackage, source_sha256 = SourceHash, pixels_sha256 = Convert.ToHexString(SHA256.HashData(pixels)), output_sha256 = Convert.ToHexString(SHA256.HashData(result)), native_acceptance = "pending" }));
    }
}
