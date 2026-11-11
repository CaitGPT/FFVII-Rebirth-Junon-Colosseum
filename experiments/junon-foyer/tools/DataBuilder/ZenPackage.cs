// An IoStore ("zen") package holding one DataObject export, as FF7 Rebirth ships
// it: a fixed summary, the name batch (each name a 2-byte big-endian length
// header, then Latin-1 or UTF-16 characters), CityHash64 name hashes, the
// import, export, bundle and graph tables, then the export's data.
//
// Only the name map and the export's size change when a table is edited, so
// everything else is carried over byte for byte.
using System.Buffers.Binary;
using System.Text;

namespace TrainingDummy.DataBuilder;

internal sealed class ZenPackage
{
    const int SummarySize = 0x40;
    readonly byte[] summary;          // the 0x40-byte summary, offsets rewritten on save
    readonly byte[] hashAlgorithm;    // the 8 bytes before the per-name hashes
    readonly List<ulong> hashes;
    readonly byte[] tables;           // imports, exports, bundles and graph data
    readonly int exportsInTables;     // where the export map starts inside `tables`
    public List<string> Names { get; }
    public byte[] Export { get; set; }

    ZenPackage(byte[] summary, List<string> names, byte[] hashAlgorithm, List<ulong> hashes, byte[] tables, int exportsInTables, byte[] export)
    {
        this.summary = summary; Names = names; this.hashAlgorithm = hashAlgorithm; this.hashes = hashes;
        this.tables = tables; this.exportsInTables = exportsInTables; Export = export;
    }

    public static ZenPackage Load(string path) => Parse(File.ReadAllBytes(path), path);

    public static ZenPackage Parse(byte[] b, string label)
    {
        int I(int o) => BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(o));
        int namesOff = I(0x18), namesSize = I(0x1c), hashesOff = I(0x20), hashesSize = I(0x24);
        int importsOff = I(0x28), exportsOff = I(0x2c), graphOff = I(0x34), graphSize = I(0x38);
        if (namesOff != SummarySize || hashesOff != (namesOff + namesSize + 7) / 8 * 8 || importsOff != hashesOff + hashesSize)
            throw new InvalidDataException($"{label}: not a zen package with the expected layout");

        var names = new List<string>();
        for (var o = namesOff; o < namesOff + namesSize;)
        {
            var wide = (b[o] & 0x80) != 0;
            var length = ((b[o] & 0x7f) << 8) | b[o + 1];
            o += 2;
            names.Add(wide ? Encoding.Unicode.GetString(b, o, 2 * length) : Encoding.Latin1.GetString(b, o, length));
            o += wide ? 2 * length : length;
        }
        var hashes = new List<ulong>();
        for (var o = hashesOff + 8; o < hashesOff + hashesSize; o += 8)
            hashes.Add(BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(o)));
        if (hashes.Count != names.Count) throw new InvalidDataException($"{label}: {names.Count} names but {hashes.Count} hashes");

        var dataStart = graphOff + graphSize;
        var exportSize = (int)BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(exportsOff + 8));
        if (dataStart + exportSize != b.Length) throw new InvalidDataException($"{label}: expected one export filling the file");
        return new ZenPackage(b[..SummarySize], names, b[hashesOff..(hashesOff + 8)], hashes,
            b[importsOff..dataStart], exportsOff - importsOff, b[dataStart..]);
    }

    /// <summary>The index of a name in the name map, appending it (with its hash) if it is new.</summary>
    public int NameIndex(string name)
    {
        var index = Names.IndexOf(name);
        if (index >= 0) return index;
        if (name.Any(c => c > 0x7f)) throw new InvalidDataException($"non-ASCII name {name}");
        Names.Add(name);
        hashes.Add(CityHash.Hash64(Encoding.ASCII.GetBytes(name.ToLowerInvariant())));
        return Names.Count - 1;
    }

    /// <summary>A name's hash as the package stores it; used to check the hash rule against vanilla names.</summary>
    public bool HashMatches(int index) =>
        Names[index].All(c => c <= 0x7f) && hashes[index] == CityHash.Hash64(Encoding.ASCII.GetBytes(Names[index].ToLowerInvariant()));

    public byte[] Save()
    {
        var names = new MemoryStream();
        foreach (var name in Names)
        {
            var wide = name.Any(c => c > 0xff);
            var bytes = wide ? Encoding.Unicode.GetBytes(name) : Encoding.Latin1.GetBytes(name);
            var length = name.Length;
            if (length > 0x7fff) throw new InvalidDataException($"name too long: {name[..32]}");
            names.WriteByte((byte)((wide ? 0x80 : 0) | (length >> 8)));
            names.WriteByte((byte)length);
            names.Write(bytes);
        }
        var namesSize = (int)names.Length;
        var hashesOff = (SummarySize + namesSize + 7) / 8 * 8;   // the hashes are 8-aligned
        var hashesSize = 8 + 8 * hashes.Count;
        var importsOff = hashesOff + hashesSize;
        var shift = importsOff - BinaryPrimitives.ReadInt32LittleEndian(summary.AsSpan(0x28));

        var head = (byte[])summary.Clone();
        void W(int o, int v) => BinaryPrimitives.WriteInt32LittleEndian(head.AsSpan(o), v);
        int R(int o) => BinaryPrimitives.ReadInt32LittleEndian(summary.AsSpan(o));
        W(0x1c, namesSize); W(0x20, hashesOff); W(0x24, hashesSize);
        foreach (var o in new[] { 0x28, 0x2c, 0x30, 0x34 }) W(o, R(o) + shift);

        var tail = (byte[])tables.Clone();
        BinaryPrimitives.WriteUInt64LittleEndian(tail.AsSpan(exportsInTables + 8), (ulong)Export.Length);

        var output = new MemoryStream();
        output.Write(head);
        names.Position = 0; names.CopyTo(output);
        output.Write(new byte[hashesOff - SummarySize - namesSize]);
        output.Write(hashAlgorithm);
        var hashBytes = new byte[8];
        foreach (var h in hashes) { BinaryPrimitives.WriteUInt64LittleEndian(hashBytes, h); output.Write(hashBytes); }
        output.Write(tail);
        output.Write(Export);
        return output.ToArray();
    }
}
