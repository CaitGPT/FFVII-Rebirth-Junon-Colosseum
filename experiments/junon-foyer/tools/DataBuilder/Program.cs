// Training Dummy data builder.
//
// Adds new rows to FF7 Rebirth DataObject tables by cloning an existing row
// and overriding named properties, as described by a JSON spec, and can
// repurpose an existing row. Other rows are never changed. Every output is
// reloaded and checked before the command reports success.
//
//   TrainingDummy.DataBuilder build     <spec.json> <vanilla-root> <output-root>
//   TrainingDummy.DataBuilder export    <input.uasset> <output.csv>
//   TrainingDummy.DataBuilder roundtrip <folder>        re-save every DataObject table and compare bytes
//   TrainingDummy.DataBuilder compare   <a.uasset> <b.uasset>   compare two tables row by row
//   TrainingDummy.DataBuilder diff      <a.uasset> <b.uasset> [max detail lines]   match rows and properties by name (game builds)
//
// <vanilla-root> and <output-root> are content roots containing
// End/Content/<asset path>, the layout UnrealReZen packs from.
using System.Buffers.Binary;
using System.Globalization;
using System.Text;
using System.Text.Json;
using TrainingDummy.DataBuilder;

return Builder.Run(args);

internal static class Builder
{
    public static int Run(string[] args)
    {
        try
        {
            if (args.Length == 6 && args[0] == "stage-raw-container") { RawContainerPack.Stage(args[1], args[2], args[3], int.Parse(args[4]), args[5]); return 0; }
            if (args.Length == 5 && args[0] == "prefix-container") { RawContainerPack.Prefix(args[1], args[2], int.Parse(args[3]), args[4]); return 0; }
            if (args.Length == 2 && args[0] == "game-build") { Console.WriteLine(RawContainerPack.Detect(args[1]).Name); return 0; }
            if (args.Length == 4 && args[0] == "clone-battle-plan") { BattlePlanPack.Clone(args[1], args[2], args[3]); return 0; }
            if (args.Length == 4 && args[0] == "layout-arrival") { LayoutPack.AddArrival(args[1], args[2], args[3]); return 0; }
            if (args.Length == 4 && args[0] == "inspect") { Inspect(args[1], args[2], args[3]); return 0; }
            if (args.Length == 4 && args[0] == "build") return Build(args[1], args[2], args[3]);
            if (args.Length == 3 && args[0] == "export") { Export(args[1], args[2]); return 0; }
            if (args.Length == 2 && args[0] == "roundtrip") return RoundTrip(args[1]);
            if (args.Length == 3 && args[0] == "compare") return Compare(args[1], args[2]);
            if (args.Length is 3 or 4 && args[0] == "diff") return Diff(args[1], args[2], args.Length == 4 ? int.Parse(args[3], CultureInfo.InvariantCulture) : 40);
            if (args.Length == 4 && args[0] == "clone-backdrop") { TexturePack.Clone(args[1], args[2], args[3]); return 0; }
            if (args.Length == 2 && args[0] == "package-chunks")
            {
                // Zen chunk ids of a package path (/Game/...): its export bundle (02) and bulk data (03).
                var id = BitConverter.GetBytes(CityHash.Hash64(System.Text.Encoding.Unicode.GetBytes(args[1].ToLowerInvariant())));
                var hex = Convert.ToHexString(id).ToLowerInvariant();
                Console.WriteLine($"{hex}00000002 {hex}00000003");
                return 0;
            }
            Console.Error.WriteLine("usage: build <spec.json> <vanilla-root> <output-root> | export <input.uasset> <output.csv>"
                + " | roundtrip <folder> | compare <a.uasset> <b.uasset>");
            return 2;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(Environment.GetEnvironmentVariable("TD_DEBUG") == "1" ? ex.ToString() : $"error: {ex.Message}");
            return 1;
        }
    }

    static int Build(string specPath, string vanillaRoot, string outputRoot)
    {
        var spec = JsonSerializer.Deserialize<Spec>(File.ReadAllText(specPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true, ReadCommentHandling = JsonCommentHandling.Skip })
            ?? throw new InvalidDataException("spec is empty");
        foreach (var tableSpec in spec.Tables)
        {
            var input = Path.Combine(vanillaRoot, "End", "Content", tableSpec.Asset);
            var output = Path.Combine(outputRoot, "End", "Content", tableSpec.Asset);
            if (Path.GetFullPath(input).Equals(Path.GetFullPath(output), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"{tableSpec.Asset}: output must not overwrite the vanilla asset");
            Directory.CreateDirectory(Path.GetDirectoryName(output));

            var table = DataTable.Load(input);
            var originalCount = table.Entries.Count;
            foreach (var row in tableSpec.Rows)
            {
                if (row.CloneFrom == null) Modify(table, row);
                else AddClone(table, row);
            }
            table.Save(output);

            Verify(input, output, originalCount, tableSpec.Rows);
            var addedCount = tableSpec.Rows.Count(r => r.CloneFrom != null);
            Console.WriteLine($"{tableSpec.Asset}: {originalCount} vanilla rows + {addedCount} new, "
                + $"{tableSpec.Rows.Count - addedCount} repurposed -> {output}");
        }
        return 0;
    }

    static void AddClone(DataTable table, RowSpec row)
    {
        if (table.RowIndex(row.Name) >= 0) throw new InvalidDataException($"row {row.Name} already exists");
        var source = table.RowIndex(row.CloneFrom);
        if (source < 0) throw new InvalidDataException($"clone source {row.CloneFrom} not found");
        var entry = table.Entries[source].Select(Copy).ToArray();
        Apply(table, entry, row);
        table.AppendRow(table.NameFor(row.Name), entry);
    }

    // Repurposes an existing row (no cloneFrom). Training Dummy's retained
    // native tests reported hangs after an exact EnemyTerritory clone, so this
    // prototype also permits reuse while diagnosing its separate arena setup.
    // That historical result is not proof of a general fixed-row-count limit.
    static void Modify(DataTable table, RowSpec row)
    {
        var index = table.RowIndex(row.Name);
        if (index < 0) throw new InvalidDataException($"row {row.Name} to repurpose not found");
        Apply(table, table.Entries[index], row);
    }

    static void Apply(DataTable table, Value[] entry, RowSpec row)
    {
        foreach (var (name, wanted) in row.Set)
        {
            var i = PropertyIndex(table, row.Name, name);
            var property = table.Properties[i];
            if (property.IsArray)
            {
                if (wanted.ValueKind != JsonValueKind.Array) throw new InvalidDataException($"{row.Name}.{name} is an array; give a JSON array");
                var items = wanted.EnumerateArray().Select(v => Parse(table, property.Type, v.ToString())).ToList();
                entry[i] = new ArrayValue(items, items.Count);
            }
            else
            {
                if (wanted.ValueKind == JsonValueKind.Array) throw new InvalidDataException($"{row.Name}.{name} is not an array");
                entry[i] = Parse(table, property.Type, wanted.ToString());
            }
        }
    }

    static int PropertyIndex(DataTable table, string row, string name)
    {
        var index = table.Properties.FindIndex(p => table.NameText(p.Name) == name);
        return index >= 0 ? index : throw new InvalidDataException($"{row}: no property {name}");
    }

    static Value Copy(Value value) => value is ArrayValue a ? new ArrayValue([.. a.Items], a.Max) : value;

    /// <summary>A value from spec text. An empty name is None; a string gets its terminator.</summary>
    static Value Parse(DataTable table, int type, string text)
    {
        var inv = CultureInfo.InvariantCulture;
        byte[] Le(long v, int size) { var b = new byte[8]; BinaryPrimitives.WriteInt64LittleEndian(b, v); return b[..size]; }
        long Integer(string s) => s.ToLowerInvariant() switch { "true" => 1, "false" => 0, _ => long.Parse(s, inv) };
        switch (type)
        {
            case DataTable.StringType: return new StringValue(text + "\0", text.Length + 1);
            case DataTable.NameType: return new NameValue(text.Length == 0 ? null : table.NameFor(text));
            case 9:
                var f = new byte[4]; BinaryPrimitives.WriteSingleLittleEndian(f, float.Parse(text, inv)); return new ScalarValue(f);
            default:
                var size = DataTable.SizeOf(type);
                var value = Integer(text);
                var bits = 8 * size;
                if (size < 8 && (value < -(1L << (bits - 1)) || value >= 1L << bits)) throw new InvalidDataException($"{text} does not fit {size} bytes");
                return new ScalarValue(Le(value, size));
        }
    }

    /// <summary>A value as text, the inverse of <see cref="Parse"/>.</summary>
    static string Format(DataTable table, int type, Value value) => value switch
    {
        StringValue s => s.Text == null ? "" : s.Text.TrimEnd('\0'),
        NameValue n => n.Name is { } name ? table.NameText(name) : "",
        ScalarValue v when type == 9 => BinaryPrimitives.ReadSingleLittleEndian(v.Bytes).ToString("R", CultureInfo.InvariantCulture),
        ScalarValue v => v.Bytes.Length switch
        {
            1 => v.Bytes[0].ToString(CultureInfo.InvariantCulture),
            2 => BinaryPrimitives.ReadInt16LittleEndian(v.Bytes).ToString(CultureInfo.InvariantCulture),
            4 => BinaryPrimitives.ReadInt32LittleEndian(v.Bytes).ToString(CultureInfo.InvariantCulture),
            _ => BinaryPrimitives.ReadInt64LittleEndian(v.Bytes).ToString(CultureInfo.InvariantCulture),
        },
        ArrayValue a => string.Join("|", a.Items.Select(i => Format(table, type, i))),
        _ => throw new InvalidDataException("unknown value"),
    };

    static void Verify(string input, string output, int originalCount, List<RowSpec> rows)
    {
        var table = DataTable.Load(output);
        var expectedCount = originalCount + rows.Count(r => r.CloneFrom != null);
        if (table.Entries.Count != expectedCount)
            throw new InvalidDataException($"{output}: expected {expectedCount} rows, found {table.Entries.Count}");
        table.CheckBuckets();
        // Every vanilla row the spec does not repurpose must read back exactly as in the vanilla asset.
        var repurposed = rows.Where(r => r.CloneFrom == null).Select(r => r.Name).ToHashSet();
        var vanilla = DataTable.Load(input);
        for (var i = 0; i < vanilla.Entries.Count; i++)
        {
            var name = vanilla.NameText(vanilla.Keys[i].Name);
            if (table.NameText(table.Keys[i].Name) != name) throw new InvalidDataException($"{output}: vanilla row {name} moved");
            if (table.HashRowIndex(table.Keys[i].Name) != i) throw new InvalidDataException($"{output}: native row {name} is not hash-reachable at its original index");
            if (!repurposed.Contains(name) && Row(vanilla, i) != Row(table, i))
                throw new InvalidDataException($"{output}: vanilla row {name} changed");
        }
        foreach (var row in rows)
        {
            var index = table.HashRowIndex(row.Name);
            if (index < 0) throw new InvalidDataException($"{output}: row {row.Name} missing after reload");
            foreach (var (name, wanted) in row.Set)
            {
                var i = PropertyIndex(table, row.Name, name);
                var actual = Format(table, table.Properties[i].Type, table.Entries[index][i]);
                var expected = wanted.ValueKind == JsonValueKind.Array ? string.Join("|", wanted.EnumerateArray().Select(v => v.ToString())) : wanted.ToString();
                if (!Same(actual, expected)) throw new InvalidDataException($"{row.Name}.{name}: wrote '{expected}', read back '{actual}'");
            }
        }
    }

    /// <summary>A row as text: each property and its value, in record order.</summary>
    static string Row(DataTable table, int index) => string.Join("\u001f", table.Properties.Select((p, i) =>
        table.NameText(p.Name) + "=" + Format(table, p.Type, table.Entries[index][i])));

    static bool Same(string actual, string expected)
    {
        if ((actual ?? "") == (expected ?? "")) return true;
        return double.TryParse(actual, CultureInfo.InvariantCulture, out var a) && double.TryParse(expected, CultureInfo.InvariantCulture, out var e) && a == e;
    }

    static void Inspect(string input, string rowName, string fieldPattern)
    {
        var table=DataTable.Load(input);
        int row=table.RowIndex(rowName);
        if(row<0) throw new InvalidDataException("Missing row "+rowName);
        var fields=new Dictionary<string,object>();
        for(int i=0;i<table.Properties.Count;i++)
        {
            var property=table.Properties[i];
            string name=table.NameText(property.Name);
            if(!System.Text.RegularExpressions.Regex.IsMatch(name,fieldPattern)) continue;
            var value=table.Entries[row][i];
            fields[name]=value is ArrayValue array
                ? array.Items.Select(x=>Format(table,property.Type,x)).ToArray()
                : Format(table,property.Type,value);
        }
        Console.WriteLine(JsonSerializer.Serialize(fields));
    }

    static void Export(string input, string output)
    {
        var table = DataTable.Load(input);
        var sb = new StringBuilder("Index,Name,Property,Value\n");
        for (var r = 0; r < table.Entries.Count; r++)
            for (var i = 0; i < table.Properties.Count; i++)
                sb.Append(r).Append(',').Append(table.NameText(table.Keys[r].Name)).Append(',').Append(table.NameText(table.Properties[i].Name))
                  .Append(",\"").Append(Format(table, table.Properties[i].Type, table.Entries[r][i]).Replace("\"", "\"\"")).Append("\"\n");
        File.WriteAllText(output, sb.ToString());
    }

    // Re-saves every DataObject table under a folder without changes. A table that is not
    // byte-identical must at least read back with the same rows.
    static int RoundTrip(string folder)
    {
        int identical = 0, equivalent = 0, skipped = 0, failed = 0;
        foreach (var path in Directory.EnumerateFiles(folder, "*.uasset", SearchOption.AllDirectories).Order())
        {
            byte[] original = File.ReadAllBytes(path);
            DataTable table;
            try
            {
                var package = ZenPackage.Parse(original, path);
                if (!package.Names.Contains("/Script/EndDataObject")) { skipped++; continue; }
                table = DataTable.Read(package, path);
            }
            catch (Exception ex) when (ex is InvalidDataException or ArgumentException or IndexOutOfRangeException) { skipped++; continue; }
            try
            {
                table.Package.Export = table.WriteExport();
                var written = table.Package.Save();
                if (written.AsSpan().SequenceEqual(original)) { identical++; continue; }
                var reread = DataTable.Read(ZenPackage.Parse(written, path), path);
                var same = reread.Entries.Count == table.Entries.Count
                    && Enumerable.Range(0, table.Entries.Count).All(i => Row(table, i) == Row(reread, i) && table.NameText(table.Keys[i].Name) == reread.NameText(reread.Keys[i].Name));
                if (same) { equivalent++; Console.WriteLine($"same rows, different bytes: {Path.GetRelativePath(folder, path)}"); }
                else { failed++; Console.WriteLine($"FAILED: {Path.GetRelativePath(folder, path)}"); }
            }
            catch (Exception ex) { failed++; Console.WriteLine($"FAILED: {Path.GetRelativePath(folder, path)}: {ex.Message}"); }
        }
        Console.WriteLine($"{identical} byte-identical, {equivalent} with identical rows, {failed} failed, {skipped} skipped");
        return failed == 0 ? 0 : 1;
    }

    static int Compare(string a, string b)
    {
        var left = DataTable.Load(a);
        var right = DataTable.Load(b);
        var differences = 0;
        if (left.Entries.Count != right.Entries.Count) { Console.WriteLine($"row count {left.Entries.Count} vs {right.Entries.Count}"); differences++; }
        for (var i = 0; i < Math.Min(left.Entries.Count, right.Entries.Count); i++)
        {
            var name = left.NameText(left.Keys[i].Name);
            if (name != right.NameText(right.Keys[i].Name)) { Console.WriteLine($"row {i}: {name} vs {right.NameText(right.Keys[i].Name)}"); differences++; continue; }
            if (Row(left, i) == Row(right, i)) continue;
            differences++;
            for (var p = 0; p < left.Properties.Count; p++)
            {
                string x = Format(left, left.Properties[p].Type, left.Entries[i][p]), y = Format(right, right.Properties[p].Type, right.Entries[i][p]);
                if (x != y) Console.WriteLine($"{name}.{left.NameText(left.Properties[p].Name)}: '{x}' vs '{y}'");
            }
        }
        Console.WriteLine(differences == 0 ? "same rows and values" : $"{differences} rows differ");
        return differences == 0 ? 0 : 1;
    }

    // Compares the same table from two game builds. `compare` walks both row lists in step, so one
    // inserted row makes every later row look changed; this matches rows and properties by name, and
    // reports the schema first, which is what says whether a build changed the format or the content.
    static int Diff(string a, string b, int maxDetail)
    {
        var left = DataTable.Load(a);
        var right = DataTable.Load(b);
        string Schema(DataTable t) => string.Join(";", t.Properties.Select(p => $"{t.NameText(p.Name)}:{p.Type}{(p.IsArray ? "[]" : "")}@{p.Offset}"));
        string leftSchema = Schema(left), rightSchema = Schema(right);

        Console.WriteLine($"unversioned properties: {left.Package.Unversioned} vs {right.Package.Unversioned}");
        Console.WriteLine($"properties: {left.Properties.Count} vs {right.Properties.Count}; row size {left.Stride} vs {right.Stride}; "
            + $"schema {(leftSchema == rightSchema ? "SAME" : "DIFFERENT")}");
        if (leftSchema != rightSchema)
        {
            List<string> Fields(DataTable t) => t.Properties.Select(p => $"{t.NameText(p.Name)}:{p.Type}{(p.IsArray ? "[]" : "")}").ToList();
            List<string> ours = Fields(left), theirs = Fields(right);
            foreach (var x in ours.Except(theirs)) Console.WriteLine($"  property removed: {x}");
            foreach (var x in theirs.Except(ours)) Console.WriteLine($"  property added: {x}");
            if (!ours.Except(theirs).Any() && !theirs.Except(ours).Any()) Console.WriteLine("  same properties, different order or offsets");
        }

        Dictionary<string, int> Rows(DataTable t) => Enumerable.Range(0, t.Keys.Count).ToDictionary(i => t.NameText(t.Keys[i].Name), i => i);
        Dictionary<string, int> leftRows = Rows(left), rightRows = Rows(right);
        var removed = leftRows.Keys.Where(k => !rightRows.ContainsKey(k)).Order().ToList();
        var added = rightRows.Keys.Where(k => !leftRows.ContainsKey(k)).Order().ToList();
        Console.WriteLine($"rows: {left.Entries.Count} vs {right.Entries.Count}");
        Console.WriteLine($"rows removed: {removed.Count}");
        foreach (var k in removed.Take(maxDetail)) Console.WriteLine($"  - {k}");
        Console.WriteLine($"rows added: {added.Count}");
        foreach (var k in added.Take(maxDetail)) Console.WriteLine($"  + {k}");

        var rightProperties = Enumerable.Range(0, right.Properties.Count).ToDictionary(p => right.NameText(right.Properties[p].Name), p => p);
        var changed = new List<string>();
        var detail = new List<string>();
        var fieldCounts = new Dictionary<string, int>();
        var moved = 0;
        foreach (var (name, i) in leftRows.OrderBy(r => r.Value))
        {
            if (!rightRows.TryGetValue(name, out var j)) continue;
            if (i != j) moved++;
            var diffs = new List<string>();
            for (var p = 0; p < left.Properties.Count; p++)
            {
                var field = left.NameText(left.Properties[p].Name);
                if (!rightProperties.TryGetValue(field, out var q)) continue;
                string x = Format(left, left.Properties[p].Type, left.Entries[i][p]), y = Format(right, right.Properties[q].Type, right.Entries[j][q]);
                if (x == y) continue;
                diffs.Add($"{field}: '{Shorten(x)}' -> '{Shorten(y)}'");
                fieldCounts[field] = fieldCounts.GetValueOrDefault(field) + 1;
            }
            if (diffs.Count == 0) continue;
            changed.Add(name);
            if (detail.Count < maxDetail)
                detail.Add($"  ~ {name}: " + string.Join("; ", diffs.Take(6)) + (diffs.Count > 6 ? $" (+{diffs.Count - 6} more)" : ""));
        }
        Console.WriteLine($"rows at a different index: {moved}");
        Console.WriteLine($"rows changed: {changed.Count}");
        foreach (var (field, n) in fieldCounts.OrderByDescending(x => x.Value)) Console.WriteLine($"  field {field}: {n} rows");
        foreach (var line in detail) Console.WriteLine(line);

        var same = leftSchema == rightSchema && removed.Count == 0 && added.Count == 0 && changed.Count == 0;
        Console.WriteLine(same ? "RESULT: same schema and rows" : "RESULT: different");
        return same ? 0 : 1;
    }

    static string Shorten(string value) => value.Length > 80 ? value[..77] + "..." : value;
}

internal sealed class Spec
{
    public List<TableSpec> Tables { get; set; } = [];
}

internal sealed class TableSpec
{
    // Path under End/Content, e.g. DataObject/Resident/Colosseum.uasset.
    public string Asset { get; set; }
    public List<RowSpec> Rows { get; set; } = [];
}

internal sealed class RowSpec
{
    public string Name { get; set; }
    public string CloneFrom { get; set; }
    public Dictionary<string, JsonElement> Set { get; set; } = [];
}
