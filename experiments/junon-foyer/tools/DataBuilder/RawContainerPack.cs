// Stage complete raw zen packages, including new maps which UnrealReZen omits
// when they have no matching native archive entry. Container metadata below
// follows the FF7R retoc Initial header reader/writer, not UE5's format.
using System.Buffers.Binary;
using System.Text;
using System.Text.Json;

namespace TrainingDummy.DataBuilder;

internal static class RawContainerPack
{
    const string Owned="JunonColosseum_999_P";
    static int I(byte[] b,int at)=>BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(at));
    static ulong Q(byte[] b,int at)=>BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(at));
    static void Require(bool ok,string why){if(!ok)throw new InvalidDataException(why);}
    static ulong Id(string path)=>CityHash.Hash64(Encoding.Unicode.GetBytes(path.ToLowerInvariant()));
    static string Chunk(ulong id,byte kind)=>Convert.ToHexString(BitConverter.GetBytes(id)).ToLowerInvariant()+"000000"+kind.ToString("x2");

    // Each owned map clones one exact native package and carries that package's
    // native store facts: export/bundle counts, load order and imports.
    // HeaderSha binds the facts to the vanilla container header they were read
    // from; OwnedPaths are the only staged paths that may carry the clone.
    // Load order and header differ per game build (the counts and imports do not),
    // so each map lists them per build.
    sealed record Native(string HeaderSha,uint LoadOrder);
    sealed record Map(string Source,ulong SourceId,string TargetLeaf,int Exports,int Bundles,ulong[] Dependencies,Dictionary<string,Native> Builds,string[] OwnedPaths);
    // A game build: the first 10 bytes of its pakchunk4optional .ucas, which our
    // container's 16-byte prefix repeats (then 6 zero bytes, as before).
    internal sealed record GameBuild(string Name,string UcasPrefix);
    static readonly GameBuild[] Builds=
    [
        new("steam-2025-01","8C060097A68897A4D300"),   // the January 2025 build our 1.0.0 was made on
        new("epic-1.005","8C0600977A889778D300"),      // 1.005_2026_0528_2133 (Epic, 2026-11-13)
    ];
    const string OldPlan="2ADC4DE2D6381D1BB674FB6C29AFD10FF06740ED011E63659DE378824164341B", EpicPlan="89E2B5FF54288F5D41E860C6759FC182936AA4076547E29CF1D49904DCE8F814";
    static string[] Regions(string leaf)=>["End/Content/Level/Game/Field/1300-JUNOA/BattlePlan/"+leaf+".umap","End/Content/Level/Game/Field/1350-JNONT/BattlePlan/"+leaf+".umap"];
    static readonly Map[] Known=
    [
        new("/Game/Level/Game/Field/2360-UNDRS/BattlePlan/2360-UNDRS_BattlePlan_Resident",0x24baea373c4fe457UL,"1300-JUNOA_BattlePlan_ModJunonColosseum",32,1,[0x920063448760ef10UL,0x0f56951f8594eb13UL],
            new(){["steam-2025-01"]=new(OldPlan,610000),["epic-1.005"]=new(EpicPlan,614107)},Regions("1300-JUNOA_BattlePlan_ModJunonColosseum")),
        new("/Game/Level/Game/Field/2360-UNDRS/BattlePlan/2360-UNDRS_BattlePlan_Resident_ServerBuild",0xd1f3ed087bf5ced5UL,"1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild",6,1,[],
            new(){["steam-2025-01"]=new(OldPlan,71801),["epic-1.005"]=new(EpicPlan,72200)},Regions("1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild")),
        // The colosseum menu backdrop (TexturePack.cs), from pakchunk3's header.
        new("/Game/Menu/Billboard/Common/U_Com_GoldSaucerArena_Bg1",0x6005b48ba5b7d1f3UL,"U_Com_JunonArena_Bg1",1,1,[],
            new(){["steam-2025-01"]=new("6E793C460AFAC90A388F5E461A819293B97E6BBD5609AF936440A3E702235FE7",262481),
                  ["epic-1.005"]=new("46F6172F5B12035882000DB64EB1E2BDE9FAC3B5B5A308197C7314AB22FD2660",264309)},["End/Content/Menu/Billboard/Common/U_Com_JunonArena_Bg1.uasset"]),
    ];
    // The game build a Paks folder holds, from its pakchunk4optional prefix; an unknown build stops the build.
    public static GameBuild Detect(string paksDir)
    {
        string probe=Path.Combine(paksDir,"pakchunk4optional-WindowsNoEditor.ucas");
        Require(File.Exists(probe),"Missing "+probe);
        byte[] head=new byte[10];
        using(var f=File.OpenRead(probe)) Require(f.Read(head,0,10)==10,"Short "+probe);
        string hex=Convert.ToHexString(head);
        return Builds.SingleOrDefault(b=>b.UcasPrefix==hex) ?? throw new InvalidDataException("Unknown game build (pakchunk4optional starts "+hex+"); add it to RawContainerPack.Builds");
    }
    // Both arena maps in two regions, plus the backdrop texture.
    public const int Registered=5;

    // factsPaths: one store-facts file per owned map, separated by ';'.
    public static void Stage(string stageRoot,string factsPaths,string output,int StagedAssets,string paksDir)
    {
        Require(!Directory.Exists(output),"Preserve prior raw container staging");
        GameBuild build=Detect(paksDir);
        Console.WriteLine("game build: "+build.Name);
        Native For(Map m)=>m.Builds.TryGetValue(build.Name,out var n)?n:throw new InvalidDataException("No native store facts for "+m.TargetLeaf+" on "+build.Name);
        Require(Id("/Game/DataObject/Resident/Action")==0x3be4c651882aeeaaUL,"Existing native Action package ID mismatch");
        byte[]? algorithm=null;
        var maps=new List<Map>();
        foreach(string factsPath in factsPaths.Split(';',StringSplitOptions.RemoveEmptyEntries))
        {
            using var facts=JsonDocument.Parse(File.ReadAllText(factsPath));
            var f=facts.RootElement;
            string source=f.GetProperty("source_package").GetString()!;
            Map map=Known.SingleOrDefault(m=>m.Source==source) ?? throw new InvalidDataException("Unknown native source package "+source);
            Require(Id(source)==map.SourceId && f.GetProperty("source_package_id").GetString()==map.SourceId.ToString("x16"),"Native package ID algorithm mismatch");
            Require(f.GetProperty("target_leaf").GetString()==map.TargetLeaf,"Unexpected owned map name");
            Require(f.GetProperty("source_container_header_sha256").GetString()==For(map).HeaderSha,"Unexpected native store metadata provenance (store facts for another game build?)");
            Require(f.GetProperty("export_count").GetInt32()==map.Exports && f.GetProperty("export_bundle_count").GetInt32()==map.Bundles && f.GetProperty("load_order").GetUInt32()==For(map).LoadOrder,"Unexpected native battle-plan metadata");
            ulong[] dependencies=f.GetProperty("imported_packages").EnumerateArray().Select(x=>Convert.ToUInt64(x.GetString(),16)).ToArray();
            Require(dependencies.SequenceEqual(map.Dependencies),"Native dependencies changed");
            byte[] a=Convert.FromHexString(f.GetProperty("native_name_hash_algorithm_hex").GetString()!);
            Require(a.SequenceEqual(Convert.FromHexString("000064c100000000")),"Unexpected native hash-algorithm bytes");
            algorithm=a;
            Require(maps.All(m=>m.Source!=source),"Duplicate store facts");
            maps.Add(map);
        }
        Require(maps.Count==Known.Length && algorithm!=null,"Every owned map needs its native store facts");
        var files=Directory.EnumerateFiles(stageRoot,"*",SearchOption.AllDirectories).Where(p=>Path.GetExtension(p) is ".uasset" or ".umap").Order(StringComparer.Ordinal).ToArray();
        Require(files.Length==StagedAssets,"Expected the composed "+StagedAssets+"-asset arena stage");
        var paths=new Dictionary<string,string>();
        var contents=new Dictionary<string,byte[]>();
        var added=new SortedDictionary<ulong,(long Size,Map Map)>();
        foreach(string file in files)
        {
            string relative=Path.GetRelativePath(stageRoot,file).Replace('\\','/');
            Require(relative.StartsWith("End/Content/",StringComparison.Ordinal) && !relative.Contains(".."),"Unscoped package path");
            string package="/Game/"+relative[12..^Path.GetExtension(file).Length];
            byte[] data=File.ReadAllBytes(file);
            Require(data.Length>=64 && I(data,0x18)==64,"Unexpected zen header");
            int at=64,end=64+I(data,0x1c);var names=new List<string>();
            while(at<end){int n=BinaryPrimitives.ReadUInt16BigEndian(data.AsSpan(at));at+=2;bool wide=(n&0x8000)!=0;int bytes=(n&0x7fff)*(wide?2:1);names.Add((wide?Encoding.Unicode:Encoding.Latin1).GetString(data,at,bytes));at+=bytes;}
            int index=I(data,0);
            Require(at==end && index>=0 && index<names.Count && string.Equals(names[index],package,StringComparison.OrdinalIgnoreCase),"Package summary/path mismatch: "+relative);
            ulong id=Id(package);string chunk=Chunk(id,2);
            Require(paths.TryAdd(chunk,"../../../"+relative) && contents.TryAdd(chunk,data),"Duplicate package ID");
            Require(!maps.Any(m=>relative.EndsWith("/"+m.TargetLeaf+Path.GetExtension(file),StringComparison.Ordinal) && !m.OwnedPaths.Contains(relative)),"Unowned new package path: "+relative);
            Map? map=maps.SingleOrDefault(m=>m.OwnedPaths.Contains(relative));
            if(map!=null)
            {
                Require((I(data,0x30)-I(data,0x2c))/72==map.Exports && I(data,I(data,0x30))==0 && I(data,I(data,0x30)+4)==map.Exports*2,"Battle-plan exports/bundle changed: "+map.TargetLeaf);
                int graph=I(data,0x34);Require(I(data,graph)==map.Dependencies.Length,"Battle-plan dependency count mismatch");
                var actual=new List<ulong>();int pos=graph+4;
                for(int j=0;j<map.Dependencies.Length;j++){actual.Add(Q(data,pos));int arcs=I(data,pos+8);Require(arcs>=0 && arcs<=64,"Unexpected dependency arcs");pos+=12+arcs*8;}
                Require(pos==graph+I(data,0x38) && actual.Order().SequenceEqual(map.Dependencies.Order()),"Battle-plan dependency graph mismatch");
                added.Add(id,(data.Length,map));
            }
        }
        Require(added.Count==Registered,"Every owned map must be present and registered in both regions");
        ulong containerId=Id(Owned);
        using var entryBytes=new MemoryStream();using(var w=new BinaryWriter(entryBytes,Encoding.UTF8,true))
        {
            int j=0,depBase=added.Count*32,depAt=0;
            foreach(var pair in added)
            {
                var m=pair.Value.Map;int entry=j*32,depStart=depBase+depAt*8;
                w.Write((ulong)pair.Value.Size);w.Write(m.Exports);w.Write(m.Bundles);w.Write(For(m).LoadOrder);w.Write(-1);
                w.Write((uint)m.Dependencies.Length);w.Write(m.Dependencies.Length==0?0u:(uint)(depStart-entry-24));
                depAt+=m.Dependencies.Length;j++;
            }
            foreach(var pair in added)foreach(ulong dep in pair.Value.Map.Dependencies)w.Write(dep);
        }
        using var header=new MemoryStream();using(var w=new BinaryWriter(header,Encoding.UTF8,true))
        {
            w.Write(containerId);w.Write((uint)added.Count);w.Write(0u); // FF7R's extra word
            w.Write(0u);w.Write(algorithm.Length);w.Write(algorithm);
            w.Write(added.Count);foreach(ulong id in added.Keys)w.Write(id);
            w.Write((int)entryBytes.Length);w.Write(entryBytes.ToArray());
            w.Write(0u);w.Write(0u); // no culture mappings or redirects
            while(header.Length%16!=0)w.Write((byte)0);
        }
        contents.Add(Chunk(containerId,10),header.ToArray());
        Directory.CreateDirectory(Path.Combine(output,"chunks"));
        foreach(var pair in contents)File.WriteAllBytes(Path.Combine(output,"chunks",pair.Key),pair.Value);
        File.WriteAllText(Path.Combine(output,"manifest.json"),JsonSerializer.Serialize(new {chunk_paths=paths,version="DirectoryIndex",mount_point="../../../"},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine(JsonSerializer.Serialize(new{chunks=contents.Count,paths=paths.Count,registered_new_packages=added.Count,container_id=containerId.ToString("x16"),game_build=build.Name,native_acceptance="pending"}));
    }

    public static void Prefix(string inputToc,string outputToc,int StagedAssets,string paksDir)
    {
        GameBuild build=Detect(paksDir);
        Require(Path.GetFileNameWithoutExtension(inputToc)==Owned && Path.GetFileNameWithoutExtension(outputToc)==Owned,"Unowned container name");
        Require(!File.Exists(outputToc) && !File.Exists(Path.ChangeExtension(outputToc,".ucas")),"Preserve prior prefixed container");
        byte[] toc=File.ReadAllBytes(inputToc),cas=File.ReadAllBytes(Path.ChangeExtension(inputToc,".ucas"));
        Require(toc.AsSpan(0,16).SequenceEqual(Convert.FromHexString("2D3D3D2D2D3D3D2D2D3D3D2D2D3D3D2D")) && toc[16]==2 && I(toc,20)==144 && I(toc,32)==12 && (toc[80]&6)==0,"Expected unsigned unencrypted DirectoryIndex container");
        int entries=I(toc,24),blocks=I(toc,28),start=144+entries*22;
        Require(entries==StagedAssets+1 && blocks>0 && start+blocks*12<=toc.Length,"Unexpected raw container table bounds");
        for(int i=0;i<blocks;i++)
        {
            int at=start+i*12;ulong offset=0;for(int j=0;j<5;j++)offset|=(ulong)toc[at+j]<<(j*8);
            int length=toc[at+5]|toc[at+6]<<8|toc[at+7]<<16;
            Require(offset+(ulong)length<=(ulong)cas.Length && offset+16<(1UL<<40),"Compressed-block range mismatch");
            ulong shifted=offset+16;for(int j=0;j<5;j++)toc[at+j]=(byte)(shifted>>(j*8));
        }
        byte[] prefix=Convert.FromHexString(build.UcasPrefix+"000000000000");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputToc))!);
        using(var output=new FileStream(Path.ChangeExtension(outputToc,".ucas"),FileMode.CreateNew)){output.Write(prefix);output.Write(cas);}
        File.WriteAllBytes(outputToc,toc);
        Require(File.ReadAllBytes(Path.ChangeExtension(outputToc,".ucas")).AsSpan(16).SequenceEqual(cas),"Container payload changed");
        Console.WriteLine(JsonSerializer.Serialize(new{native_prefix_bytes=16,game_build=build.Name,shifted_physical_blocks=blocks,chunk_payloads_unchanged=true,native_acceptance="pending"}));
    }
}
