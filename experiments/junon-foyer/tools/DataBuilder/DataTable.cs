// A DataObject table: the frozen UE memory image inside a zen package's export.
//
// Export: a property prefix, a 32-bit frozen size, padding to +0x20, then the
// frozen image, 8 bytes, the name patch table and 4 trailing bytes.
//
// The prefix comes in the two shapes the game ships. A versioned export (the
// 2024 Steam build) starts with an 8-byte tagged "None" property, putting the
// frozen size at +0x0c. An unversioned one (the Epic 1.005 build, flagged
// PKG_UnversionedProperties in the package summary) starts with a 2-byte
// FUnversionedHeader instead, putting the size at +0x06. Both pad the prefix to
// 0x20, so the frozen image and everything after it are laid out the same way,
// and a table is saved back in the format it was read in.
//
// Frozen image (offsets from its start; pointers are int64 (relative offset << 1) | 1):
//   0x00 row keys: TSet<TPair<FName,int32>> = sparse array {ptr, num, max}, allocation
//        bits {ptr, numBits, maxBits}, firstFree, numFree; then bucket array {ptr, size}
//   0x38 property records {ptr, num, max}: 12 bytes each, FName + type code
//   0x48 entries {ptr, num, max}: one struct per row, fields in record order
//   0x58 key elements (20 bytes: FName, entry index, next in bucket, bucket), the
//        allocation bits, the buckets, the property records, the entries (8-aligned),
//        then array and string contents, depth first, and the image is padded to 16.
// A field whose name ends in "_Array" is a TArray of its type (16 bytes in the row).
// Strings are UTF-16 with the terminator counted. Every FName is stored as zero and
// named by the patch table: {name index, number, count, offsets}.
//
// The game's writer shares identical content: strings with equal characters, and
// arrays (other than string arrays, whose pointers make their bytes unique) with
// equal bytes, names and alignment. Writing with the same rule reproduces 1,689 of
// the 1,694 shipped DataObject tables byte for byte; the other five reuse bytes from
// inside the key table for tiny arrays, where this writer stores its own copy.
using System.Buffers.Binary;
using System.Text;

namespace TrainingDummy.DataBuilder;

internal readonly record struct NameRef(int Index, int Number);

internal sealed record Property(NameRef Name, int Type, bool IsArray, int Offset);

internal sealed class RowKey
{
    public NameRef Name;
    public int Index, Next, Bucket;
}

/// <summary>A field value: <see cref="ScalarValue"/>, <see cref="StringValue"/>, <see cref="NameValue"/> or <see cref="ArrayValue"/>.</summary>
internal abstract record Value;
internal sealed record ScalarValue(byte[] Bytes) : Value
{
    public bool Equals(ScalarValue other) => other != null && Bytes.AsSpan().SequenceEqual(other.Bytes);
    public override int GetHashCode() => Convert.ToHexString(Bytes).GetHashCode();
}
/// <summary>Text includes its terminating NUL; null is an empty (unallocated) string.</summary>
internal sealed record StringValue(string Text, int Max) : Value;
internal sealed record NameValue(NameRef? Name) : Value;
internal sealed record ArrayValue(List<Value> Items, int Max) : Value
{
    public bool Equals(ArrayValue other) => other != null && Max == other.Max && Items.SequenceEqual(other.Items);
    public override int GetHashCode() => Items.Count;
}

internal sealed class DataTable
{
    // Type codes: element size (alignment is the same, except strings and names).
    static readonly Dictionary<int, int> Sizes = new() { [1] = 1, [2] = 1, [3] = 1, [4] = 2, [6] = 4, [7] = 4, [8] = 8, [9] = 4, [10] = 16, [11] = 8 };
    public const int StringType = 10, NameType = 11;

    public ZenPackage Package { get; }
    byte[] prefix, prePatch, tail;
    int keysMax, bitsMax, firstFree, numFree, propsMax, entriesMax;
    byte[] hashPad;
    public List<RowKey> Keys { get; } = [];
    public List<int> Buckets { get; } = [];
    public List<Property> Properties { get; } = [];
    public List<Value[]> Entries { get; } = [];
    public int Stride { get; private set; }
    int entryAlign;

    DataTable(ZenPackage package) => Package = package;

    /// <summary>Where the export keeps its frozen size: after an unversioned header, or after a tagged "None".</summary>
    static int FrozenSizeOffset(ZenPackage package) => package.Unversioned ? 0x06 : 0x0c;

    public static int SizeOf(int type) => Sizes.TryGetValue(type, out var s) ? s : throw new InvalidDataException($"unknown property type {type}");
    static int AlignOf(int type) => type == StringType ? 8 : type == NameType ? 4 : SizeOf(type);
    static int AlignUp(int x, int a) => (x + a - 1) / a * a;

    public static DataTable Load(string path) => Read(ZenPackage.Load(path), path);

    public static DataTable Read(ZenPackage package, string label)
    {
        var t = new DataTable(package);
        var b = package.Export;
        int I(int o) => BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(o));
        var frozenSize = I(FrozenSizeOffset(package));
        const int baseOff = 0x20;
        var end = baseOff + frozenSize;
        if (end + 12 > b.Length) throw new InvalidDataException($"{label}: frozen image runs past the export");
        t.prefix = b[..baseOff];
        t.prePatch = b[end..(end + 8)];

        var patches = new Dictionary<int, NameRef>();
        var o = end + 8;
        var count = I(o); o += 4;
        for (var i = 0; i < count; i++)
        {
            var name = new NameRef(I(o), I(o + 4));
            var n = I(o + 8); o += 12;
            if (name.Index < 0 || name.Index >= package.Names.Count) throw new InvalidDataException($"{label}: bad name index {name.Index}");
            for (var k = 0; k < n; k++, o += 4) patches[I(o)] = name;
        }
        t.tail = b[o..];
        NameRef? NameAt(int pos) => patches.TryGetValue(pos - baseOff, out var n) ? n : null;
        int Ptr(int pos)
        {
            var p = BinaryPrimitives.ReadInt64LittleEndian(b.AsSpan(pos));
            if ((p & 1) == 0) throw new InvalidDataException($"{label}: unfrozen pointer at {pos:x}");
            return (int)(pos + (p >> 1));
        }

        var keysPtr = Ptr(baseOff); var keyCount = I(baseOff + 8); t.keysMax = I(baseOff + 0x0c);
        t.bitsMax = I(baseOff + 0x1c); t.firstFree = I(baseOff + 0x20); t.numFree = I(baseOff + 0x24);
        var hashPtr = Ptr(baseOff + 0x28); var hashSize = I(baseOff + 0x30); t.hashPad = b[(baseOff + 0x34)..(baseOff + 0x38)];
        var propsPtr = Ptr(baseOff + 0x38); var propCount = I(baseOff + 0x40); t.propsMax = I(baseOff + 0x44);
        var entriesPtr = Ptr(baseOff + 0x48); var entryCount = I(baseOff + 0x50); t.entriesMax = I(baseOff + 0x54);
        if (t.firstFree != -1 || t.numFree != 0 || entryCount != keyCount)
            throw new InvalidDataException($"{label}: row map is not dense");

        for (var i = 0; i < keyCount; i++)
        {
            var k = keysPtr + 20 * i;
            t.Keys.Add(new RowKey { Name = NameAt(k) ?? throw new InvalidDataException($"{label}: unnamed key {i}"), Index = I(k + 8), Next = I(k + 12), Bucket = I(k + 16) });
        }
        for (var i = 0; i < hashSize; i++) t.Buckets.Add(I(hashPtr + 4 * i));

        var offset = 0; t.entryAlign = 1;
        for (var i = 0; i < propCount; i++)
        {
            var p = propsPtr + 12 * i;
            var name = NameAt(p) ?? throw new InvalidDataException($"{label}: unnamed property {i}");
            var type = I(p + 8);
            var isArray = package.Names[name.Index].EndsWith("_Array", StringComparison.Ordinal);
            int size = isArray ? 16 : SizeOf(type), align = isArray ? 8 : AlignOf(type);
            offset = AlignUp(offset, align);
            t.Properties.Add(new Property(name, type, isArray, offset));
            offset += size; t.entryAlign = Math.Max(t.entryAlign, align);
        }
        t.Stride = AlignUp(offset, t.entryAlign);

        StringValue ReadString(int pos)
        {
            var n = I(pos + 8);
            return new StringValue(n == 0 ? null : Encoding.Unicode.GetString(b, Ptr(pos), 2 * n), I(pos + 12));
        }
        Value ReadField(int pos, Property p)
        {
            if (p.IsArray)
            {
                var n = I(pos + 8); var items = new List<Value>(n);
                if (n > 0)
                {
                    var data = Ptr(pos); var size = SizeOf(p.Type);
                    for (var k = 0; k < n; k++)
                    {
                        var e = data + size * k;
                        items.Add(p.Type == StringType ? ReadString(e) : p.Type == NameType ? new NameValue(NameAt(e)) : new ScalarValue(b[e..(e + size)]));
                    }
                }
                return new ArrayValue(items, I(pos + 12));
            }
            return p.Type == StringType ? ReadString(pos) : p.Type == NameType ? new NameValue(NameAt(pos)) : new ScalarValue(b[pos..(pos + SizeOf(p.Type))]);
        }
        for (var e = 0; e < entryCount; e++)
        {
            var row = new Value[propCount];
            for (var i = 0; i < propCount; i++) row[i] = ReadField(entriesPtr + t.Stride * e + t.Properties[i].Offset, t.Properties[i]);
            t.Entries.Add(row);
        }
        return t;
    }

    /// <summary>The export bytes for the current keys, buckets and entries.</summary>
    public byte[] WriteExport()
    {
        var w = new FrozenWriter();
        w.Alloc(0x58, 8);
        var keys = w.Alloc(20 * Keys.Count, 4);
        for (var i = 0; i < Keys.Count; i++)
        {
            var k = keys + 20 * i;
            w.Name(k, Keys[i].Name); w.Int(k + 8, Keys[i].Index); w.Int(k + 12, Keys[i].Next); w.Int(k + 16, Keys[i].Bucket);
        }
        var bits = w.Alloc(4 * ((bitsMax + 31) / 32), 4);
        for (var i = 0; i < Keys.Count; i++) w.Buffer[bits + i / 8] |= (byte)(1 << (i % 8));
        var hash = w.Alloc(4 * Buckets.Count, 4);
        for (var i = 0; i < Buckets.Count; i++) w.Int(hash + 4 * i, Buckets[i]);
        var props = w.Alloc(12 * Properties.Count, 4);
        for (var i = 0; i < Properties.Count; i++) { w.Name(props + 12 * i, Properties[i].Name); w.Int(props + 12 * i + 8, Properties[i].Type); }
        var entries = w.Alloc(Stride * Entries.Count, entryAlign);

        w.Ptr(0, keys); w.Int(8, Keys.Count); w.Int(0x0c, keysMax);
        w.Ptr(0x10, bits); w.Int(0x18, Keys.Count); w.Int(0x1c, bitsMax); w.Int(0x20, firstFree); w.Int(0x24, numFree);
        w.Ptr(0x28, hash); w.Int(0x30, Buckets.Count); hashPad.CopyTo(w.Buffer, 0x34);
        w.Ptr(0x38, props); w.Int(0x40, Properties.Count); w.Int(0x44, propsMax);
        w.Ptr(0x48, entries); w.Int(0x50, Entries.Count); w.Int(0x54, entriesMax);

        for (var e = 0; e < Entries.Count; e++)
            for (var i = 0; i < Properties.Count; i++)
                w.Field(entries + Stride * e + Properties[i].Offset, Properties[i], Entries[e][i]);
        var frozen = w.Finish(16);

        var output = new MemoryStream();
        var head = (byte[])prefix.Clone();
        BinaryPrimitives.WriteInt32LittleEndian(head.AsSpan(FrozenSizeOffset(Package)), frozen.Length);
        output.Write(head); output.Write(frozen); output.Write(prePatch);
        var groups = w.Patches.OrderBy(g => g.Key.Index).ThenBy(g => g.Key.Number).ToList();
        void Int(int v) { Span<byte> s = stackalloc byte[4]; BinaryPrimitives.WriteInt32LittleEndian(s, v); output.Write(s); }
        Int(groups.Count);
        foreach (var (name, offsets) in groups)
        {
            Int(name.Index); Int(name.Number); Int(offsets.Count);
            foreach (var o in offsets.Order()) Int(o);
        }
        output.Write(tail);
        return output.ToArray();
    }

    /// <summary>Writes the package with the current table to <paramref name="path"/>.</summary>
    public void Save(string path)
    {
        Package.Export = WriteExport();
        File.WriteAllBytes(path, Package.Save());
    }

    /// <summary>A row's display name, as UE prints an FName: name, or name_(number - 1).</summary>
    public string NameText(NameRef name) => name.Number == 0 ? Package.Names[name.Index] : $"{Package.Names[name.Index]}_{name.Number - 1}";

    /// <summary>An FName for text, splitting a numeric suffix as UE does ("Boss_10" is "Boss" number 11).</summary>
    public NameRef NameFor(string text)
    {
        var cut = text.LastIndexOf('_');
        if (cut > 0 && cut < text.Length - 1)
        {
            var digits = text[(cut + 1)..];
            if (digits.All(char.IsAsciiDigit) && (digits.Length == 1 || digits[0] != '0') && int.TryParse(digits, out var n))
                return new NameRef(Package.NameIndex(text[..cut]), n + 1);
        }
        return new NameRef(Package.NameIndex(text), 0);
    }

    public int RowIndex(string name) => Keys.FindIndex(k => NameText(k.Name) == name);

    /// <summary>Find through the frozen TMap bucket chain, never a linear scan.</summary>
    public int HashRowIndex(string text)
    {
        var plain = text;
        int number = 0, cut = text.LastIndexOf('_');
        if (cut > 0 && cut < text.Length - 1)
        {
            var digits = text[(cut + 1)..];
            if (digits.All(char.IsAsciiDigit) && (digits.Length == 1 || digits[0] != '0') && int.TryParse(digits, out var n))
            { plain = text[..cut]; number = checked(n + 1); }
        }
        int nameIndex = Package.Names.FindIndex(n => string.Equals(n, plain, StringComparison.OrdinalIgnoreCase));
        return nameIndex < 0 ? -1 : HashRowIndex(new NameRef(nameIndex, number));
    }

    public int HashRowIndex(NameRef name)
    {
        if (Buckets.Count == 0) return -1;
        string plain = Package.Names[name.Index];
        int number = name.Number;
        int bucket = BucketOf(name, Buckets.Count);
        int cursor = Buckets[bucket];
        for (int steps = 0; cursor != -1; steps++)
        {
            if (cursor < 0 || cursor >= Keys.Count || steps >= Keys.Count)
                throw new InvalidDataException($"Invalid hash chain while finding {NameText(name)}");
            var key = Keys[cursor];
            if (key.Name.Number == number && string.Equals(Package.Names[key.Name.Index], plain, StringComparison.OrdinalIgnoreCase))
                return key.Index;
            cursor = key.Next;
        }
        return -1;
    }

    // TSet buckets: RoundUpToPowerOfTwo(Num / 2 + 8) from 4 elements; the bucket is
    // CityHash64(lowercase plain name) + FName number, masked to the bucket count.
    public static int BucketCount(int elements)
    {
        if (elements < 4) return 1;
        var size = 1;
        while (size < elements / 2 + 8) size <<= 1;
        return size;
    }

    public int BucketOf(NameRef name, int bucketCount)
    {
        var plain = Package.Names[name.Index].ToLowerInvariant();
        // FName stores non-ANSI comparison strings as UTF-16LE. Validate this
        // branch against the original frozen bucket graph before any append.
        var bytes = plain.Any(c => c > 0x7f) ? Encoding.Unicode.GetBytes(plain) : Encoding.ASCII.GetBytes(plain);
        var hash = CityHash.Hash64(bytes) + (ulong)name.Number;
        return (int)(hash & (ulong)(bucketCount - 1));
    }

    /// <summary>Appends a row and links its key, rehashing every key if the bucket count grows.</summary>
    public void AppendRow(NameRef name, Value[] entry)
    {
        CheckBuckets();
        Keys.Add(new RowKey { Name = name, Index = Entries.Count, Next = -1 });
        Entries.Add(entry);
        keysMax = Math.Max(keysMax, Keys.Count);
        entriesMax = Math.Max(entriesMax, Entries.Count);
        bitsMax = Math.Max(bitsMax, AlignUp(Keys.Count, 32));
        var size = BucketCount(Keys.Count);
        if (size != Buckets.Count)
        {
            Buckets.Clear();
            Buckets.AddRange(Enumerable.Repeat(-1, size));
            for (var i = 0; i < Keys.Count; i++) Link(i);
        }
        else Link(Keys.Count - 1);
        CheckBuckets();
    }

    void Link(int position)
    {
        var key = Keys[position];
        key.Bucket = BucketOf(key.Name, Buckets.Count);
        key.Next = Buckets[key.Bucket];
        Buckets[key.Bucket] = position;
    }

    /// <summary>Every key must sit in the bucket its name hashes to and be reachable from that bucket's chain.</summary>
    public void CheckBuckets()
    {
        for (var i = 0; i < Keys.Count; i++)
        {
            var bucket = BucketOf(Keys[i].Name, Buckets.Count);
            if (Keys[i].Bucket != bucket || Keys[i].Index != i)
                throw new InvalidDataException($"key {NameText(Keys[i].Name)}: bucket {Keys[i].Bucket}, expected {bucket}");
            var cursor = Buckets[bucket];
            for (var steps = 0; cursor != i; steps++)
            {
                if (cursor == -1 || steps > Keys.Count) throw new InvalidDataException($"key {NameText(Keys[i].Name)} is not reachable from bucket {bucket}");
                cursor = Keys[cursor].Next;
            }
        }
    }

    sealed class FrozenWriter
    {
        public byte[] Buffer = new byte[4096];
        int length;
        public readonly Dictionary<NameRef, List<int>> Patches = [];
        readonly Dictionary<string, int> shared = [];

        public int Alloc(int size, int align)
        {
            var pos = AlignUp(length, align);
            Grow(pos + size);
            length = pos + size;
            return pos;
        }

        void Grow(int size)
        {
            if (size <= Buffer.Length) return;
            Array.Resize(ref Buffer, Math.Max(size, Buffer.Length * 2));
        }

        public void Int(int pos, int value) => BinaryPrimitives.WriteInt32LittleEndian(Buffer.AsSpan(pos), value);
        public void Ptr(int pos, int target) => BinaryPrimitives.WriteInt64LittleEndian(Buffer.AsSpan(pos), ((long)(target - pos) << 1) | 1);
        public void Name(int pos, NameRef? name)
        {
            if (name is not { } n) return;
            if (!Patches.TryGetValue(n, out var list)) Patches[n] = list = [];
            list.Add(pos);
        }

        public byte[] Finish(int align)
        {
            var size = AlignUp(length, align);
            Grow(size);
            return Buffer[..size];
        }

        void String(int pos, StringValue value)
        {
            if (value.Text == null) { Int(pos + 8, 0); Int(pos + 12, value.Max); return; }
            var data = Encoding.Unicode.GetBytes(value.Text);
            var key = "s:" + Convert.ToBase64String(data);
            if (!shared.TryGetValue(key, out var target))
            {
                target = Alloc(data.Length, 2);
                data.CopyTo(Buffer, target);
                shared[key] = target;
            }
            Ptr(pos, target); Int(pos + 8, value.Text.Length); Int(pos + 12, value.Max);
        }

        public void Field(int pos, Property p, Value value)
        {
            if (!p.IsArray)
            {
                switch (value)
                {
                    case StringValue s: String(pos, s); break;
                    case NameValue n: Name(pos, n.Name); break;
                    case ScalarValue v: v.Bytes.CopyTo(Buffer, pos); break;
                    default: throw new InvalidDataException($"field type mismatch at {pos:x}");
                }
                return;
            }
            var array = (ArrayValue)value;
            if (array.Items.Count == 0) { Int(pos + 8, 0); Int(pos + 12, array.Max); return; }
            var size = SizeOf(p.Type);
            var align = AlignOf(p.Type);
            // A string array holds pointers relative to itself, so its bytes never repeat: it is never shared.
            var key = p.Type == StringType ? null
                : p.Type == NameType ? $"n{align}:" + string.Join(",", array.Items.Select(i => ((NameValue)i).Name is { } n ? $"{n.Index}.{n.Number}" : "-"))
                : $"b{align}:" + Convert.ToBase64String(array.Items.SelectMany(i => ((ScalarValue)i).Bytes).ToArray());
            if (key == null || !shared.TryGetValue(key, out var target))
            {
                target = Alloc(size * array.Items.Count, align);
                if (key != null) shared[key] = target;
                for (var k = 0; k < array.Items.Count; k++)
                {
                    var e = target + size * k;
                    switch (array.Items[k])
                    {
                        case StringValue s: String(e, s); break;
                        case NameValue n: Name(e, n.Name); break;
                        case ScalarValue v: v.Bytes.CopyTo(Buffer, e); break;
                    }
                }
            }
            Ptr(pos, target); Int(pos + 8, array.Items.Count); Int(pos + 12, array.Max);
        }
    }
}
