// Use Unreal's own Rename operation before finishing our deferred actor.
// No raw UObject name writes, menu calls, save writes or game input.
#include <Mod/CppUserModBase.hpp>
#include <Unreal/AActor.hpp>
#include <Unreal/UObject.hpp>
#include <Unreal/UClass.hpp>
#include <Unreal/UObjectGlobals.hpp>
#include <Unreal/UObjectArray.hpp>
#include <Unreal/FWeakObjectPtr.hpp>
#include <Unreal/UFunction.hpp>
#include <Unreal/TArray.hpp>
#include <Unreal/FProperty.hpp>
#include <Unreal/FString.hpp>
#include <Unreal/Property/FBoolProperty.hpp>
#include <Unreal/Property/FObjectProperty.hpp>
#include <Unreal/Property/FSoftObjectProperty.hpp>
#include <Unreal/Property/FStrProperty.hpp>
#include <Unreal/Property/FStructProperty.hpp>
#include <windows.h>
#include <tlhelp32.h>
#include <chrono>
#include <thread>
#include <cmath>
#include <filesystem>
#include <unordered_map>
#include <cstdint>
#include <fstream>
#include <functional>
#include <vector>
#include <string>
#include <cstring>
#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <atomic>
#include <cwchar>

// Exact callback declaration used by the installed telemetry exporter for
// UE4SS c0a8d4c / UEPseudo b4a6e7e. No LuaMadeSimple ABI crossing.
namespace RC::Unreal::Hook
{
    using ProcessEventCallback = std::function<void(UObject*, UFunction*, void*)>;
    RC_UE_API auto RegisterProcessEventPreCallback(ProcessEventCallback) -> void;
}

namespace
{
    constexpr auto BoardName = STR("oblMod_JunonColosseum_Noticeboard");

    // Where this mod's files live, on any machine: its folder is two levels above
    // this DLL (Mods/<mod>/dlls/main.dll). On development installs dev.txt there
    // names a telemetry folder; releases have none, so every Dev() path is empty
    // (log writes fail quietly and diagnostic switch files never exist).
    int marker=0;
    std::filesystem::path ModDir()
    {
        static const std::filesystem::path dir=[]{
            HMODULE self=nullptr;
            GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               reinterpret_cast<LPCWSTR>(&marker),&self);
            wchar_t buffer[4096]{};
            GetModuleFileNameW(self,buffer,4096);
            return std::filesystem::path(buffer).parent_path().parent_path();
        }();
        return dir;
    }
    std::string Dev(const char* name)
    {
        static const std::string dir=[]{
            std::ifstream in(ModDir()/"dev.txt");
            std::string line;
            std::getline(in,line);
            while(!line.empty() && (line.back()=='\r' || line.back()==' ')) line.pop_back();
            if(!line.empty() && line.back()!='/' && line.back()!='\\') line+='/';
            return line;
        }();
        return dir.empty() ? std::string() : dir+name;
    }
    bool DevFlag(const char* name)
    {
        const auto path=Dev(name);
        std::error_code ec;
        return !path.empty() && std::filesystem::exists(path,ec);
    }
    std::string Shared(const char* name) { return (ModDir()/name).string(); }
    // Load one owned level by exact package path. The first call truncates the
    // trace; later calls in the same request append to it.
    bool LoadOwnedLevel(RC::Unreal::UObject* context,const wchar_t* packagePath,const wchar_t* leafName,bool appendTrace)
    {
        using namespace RC::Unreal;
        auto* api=UObjectGlobals::StaticFindObject<UObject*>(nullptr,nullptr,STR("/Script/Engine.Default__LevelStreamingDynamic"));
        auto* fn=UObjectGlobals::StaticFindObject<UFunction*>(nullptr,nullptr,STR("/Script/Engine.LevelStreamingDynamic:LoadLevelInstance"));
        std::ofstream trace(Dev("junon-native-plan-load.tsv"),appendTrace?std::ios::app:std::ios::trunc);
        {
            const std::wstring leafText(leafName);
            trace<<"level\t"<<std::string(leafText.begin(),leafText.end())<<"\n";
        }
        auto refuse=[&](const char* reason){trace<<"refused\t"<<reason<<"\n";return false;};
        if(!api || !fn)return refuse("function_or_default_missing");
        trace<<"method\tLoadLevelInstance\nnum_params\t"<<int(fn->GetNumParms())<<"\nproperties_size\t"<<fn->GetPropertiesSize()<<"\nsizeof_fstring\t"<<sizeof(FString)<<"\n";
        if(fn->GetNumParms()!=7 || fn->GetPropertiesSize()<8 || fn->GetPropertiesSize()>256)return refuse("unexpected_parameter_block");
        struct Parameters {
            std::vector<uint8_t> bytes;
            std::vector<FProperty*> fields;
            ~Parameters(){for(auto it=fields.rbegin();it!=fields.rend();++it)(*it)->DestroyValue_InContainer(bytes.data());}
        } params{std::vector<uint8_t>(fn->GetPropertiesSize()),{}};
        FProperty *world=nullptr,*path=nullptr,*location=nullptr,*rotation=nullptr,*success=nullptr,*name=nullptr,*result=nullptr;
        for(auto* field:fn->ForEachProperty()){
            if(!field->HasAnyPropertyFlags(CPF_Parm))continue;
            const auto fieldName=field->GetName();
            trace<<"field\t"<<std::string(fieldName.begin(),fieldName.end())<<"\t"<<field->GetOffset_Internal()<<"\t"<<field->GetElementSize()<<"\t"<<field->GetArrayDim()
                 <<"\tobject="<<field->IsA<FObjectProperty>()<<"\tstring="<<field->IsA<FStrProperty>()<<"\tstruct="<<field->IsA<FStructProperty>()<<"\tbool="<<field->IsA<FBoolProperty>()<<"\n";
            if(field->GetArrayDim()!=1 || field->GetOffset_Internal()<0 || field->GetElementSize()<1 ||
               field->GetOffset_Internal()+field->GetElementSize()>fn->GetPropertiesSize()) return refuse("field_outside_parameter_block");
            field->InitializeValue_InContainer(params.bytes.data());params.fields.push_back(field);
            const auto n=field->GetName();
            if(n==STR("WorldContextObject"))world=field;
            else if(n==STR("LevelName"))path=field;
            else if(n==STR("Location"))location=field;
            else if(n==STR("Rotation"))rotation=field;
            else if(n==STR("bOutSuccess"))success=field;
            else if(n==STR("OptionalLevelNameOverride"))name=field;
            else if(n==STR("ReturnValue"))result=field;
            else return refuse("unknown_parameter");
        }
        if(params.fields.size()!=7 || !world || !path || !name || !location || !rotation || !success || !result ||
           !world->IsA<FObjectProperty>() || !path->IsA<FStrProperty>() || !name->IsA<FStrProperty>() ||
           !location->IsA<FStructProperty>() || !rotation->IsA<FStructProperty>() ||
           !success->IsA<FBoolProperty>() || !result->IsA<FObjectProperty>() ||
           location->GetElementSize()!=12 || rotation->GetElementSize()!=12 ||
           world->GetElementSize()!=sizeof(UObject*) || result->GetElementSize()!=sizeof(UObject*) ||
           path->GetElementSize()!=sizeof(FString) || name->GetElementSize()!=sizeof(FString)) return refuse("parameter_type_or_size");
        FString leaf(leafName);
        world->CopySingleValue(world->ContainerPtrToValuePtr<void>(params.bytes.data()),&context);
        FString package(packagePath);
        path->CopySingleValue(path->ContainerPtrToValuePtr<void>(params.bytes.data()),&package);
        name->CopySingleValue(name->ContainerPtrToValuePtr<void>(params.bytes.data()),&leaf);
        // Initialized Vector/Rotator parameters remain zero: the owned maps are
        // already relocated. Every offset/size comes from reflected metadata.
        api->ProcessEvent(fn,params.bytes.data());
        const bool ok=static_cast<FBoolProperty*>(success)->GetPropertyValueInContainer(params.bytes.data());
        const bool returned=*result->ContainerPtrToValuePtr<UObject*>(params.bytes.data())!=nullptr;
        trace<<"native_dispatched\t1\nsuccess\t"<<ok<<"\nreturned_stream\t"<<returned<<"\n";
        return ok && returned;
    }
    // The plan holds the arena's territory actor, points and cameras. Its
    // ServerBuild companion holds the same-named server-build actor whose enemy
    // spawn/summon lists the territory uses, as in the native prison arena.
    // Lua requests the ServerBuild level first and the plan only once that is
    // loaded and visible: natively it loads first (store load order 71801
    // against the plan's 610000), so the territory actor may look its
    // server-build actor up when it begins play. AK loaded both together and
    // the battle still stalled.

    // Live 2026-11-10, load crash A (EXCEPTION_ACCESS_VIOLATION writing 0x39 at
    // ff7rebirth_.exe+0x872ceb): this game calls ProcessEvent from TaskGraph
    // worker threads, and UE4SS 3.0.1 runs ExecuteInGameThread work (our Lua
    // tick) and this callback on whichever thread calls ProcessEvent next. The
    // async loader keeps per-thread state (TLS slot read by FlushLoading at
    // +0x872a58 from exe+0x870e42c) only on the game thread and the loading
    // thread; a load flushed from a worker writes through null. So anything
    // that loads, edits tables or touches party data runs only on a thread
    // that has that state. The slot is found per known build and checked
    // against FlushLoading's own code (mov ecx,[rip+disp32] at +0xac reads the
    // slot). On a build none of them matches, the guard answers "not the game
    // thread" everywhere, so the helper does no engine work at all rather than
    // run it from worker threads (2026-11-13; it used to allow all).
    struct LoaderTlsBuild { const char* name; uintptr_t flushLoading; uintptr_t slot; };
    constexpr LoaderTlsBuild LoaderTlsBuilds[]={
        {"steam-2025-01",0x872a58,0x870e42c},   // ff7rebirth_.exe sha256 37D952FA...
        {"epic-1.005",0x795590,0x8640bbc},      // 1.005_2026_0528_2133, sha256 73D13281... (derived offline 2026-11-13)
    };
    // Plain function (no C++ objects) so __try may guard the code read.
    bool ReadsLoaderSlot(const uint8_t* fn,const uint8_t* want)
    {
        __try {
            if(fn[0xac]!=0x8B || fn[0xad]!=0x0D) return false;
            int32_t disp; std::memcpy(&disp,fn+0xae,4);
            return fn+0xac+6+disp==want;
        } __except(1) { return false; }
    }
    // The game build this executable is (index into LoaderTlsBuilds), or -1. Every
    // per-build address table below is indexed by it; each feature still checks its
    // own code bytes before use.
    enum GameBuildId { SteamJan2025=0, Epic1005=1 };
    int GameBuild()
    {
        static const int build=[]{
            const auto base=reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
            for(int i=0;i<int(std::size(LoaderTlsBuilds));++i)
                if(ReadsLoaderSlot(base+LoaderTlsBuilds[i].flushLoading,base+LoaderTlsBuilds[i].slot)){
                    std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<"game_thread_guard_ready "<<LoaderTlsBuilds[i].name<<"\n";
                    return i;
                }
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<"game_thread_guard_unverified_unknown_build helper_engine_work_off\n";
            return -1;
        }();
        return build;
    }
    bool OnGameThread()
    {
        static const DWORD* slot=[]()->const DWORD*{
            const int build=GameBuild();
            if(build<0) return nullptr;
            return reinterpret_cast<const DWORD*>(reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr))+LoaderTlsBuilds[build].slot);
        }();
        if(!slot) return false;
        const DWORD index=*slot;
        if(index>=1088) return false;  // TLS_MINIMUM_AVAILABLE + expansion slots
        return TlsGetValue(index)!=nullptr;
    }
    // This executable's code, checked byte for byte before any address is used
    // (image base 0x140000000; "48 8B ..." hex text, rel32/RIP displacements
    // included, so callees and globals are pinned too, as InfusionSkills does).
    namespace Code
    {
        constexpr uintptr_t ImageBase=0x140000000;
        uintptr_t Base(){ static const uintptr_t base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)); return base; }
        uintptr_t At(uintptr_t va){ return va-ImageBase+Base(); }
        bool Byte(uintptr_t at,uint8_t& out){ __try { out=*reinterpret_cast<const uint8_t*>(at); return true; } __except(1) { return false; } }
        bool Qword(uintptr_t at,uint64_t& out){ if(at<0x10000) return false; __try { out=*reinterpret_cast<const uint64_t*>(at); return true; } __except(1) { return false; } }
        int Nibble(char c){ return c>='0'&&c<='9'?c-'0':c>='A'&&c<='F'?c-'A'+10:c>='a'&&c<='f'?c-'a'+10:-1; }
        bool Matches(uintptr_t va,const char* bytes)
        {
            uintptr_t at=At(va);
            for(const char* p=bytes;;){
                while(*p==' ') ++p;
                if(!*p) return true;
                const int hi=Nibble(p[0]), lo=hi<0?-1:Nibble(p[1]);
                uint8_t got=0;
                if(lo<0 || !Byte(at++,got) || got!=uint8_t(hi*16+lo)) return false;
                p+=2;
            }
        }
        // The instruction at va starts with opcode (hex) and its RIP-relative
        // disp32 (right after the opcode) points at target; length is the whole
        // instruction's size. Pins a global without spelling out its displacement.
        bool RipTargets(uintptr_t va,const char* opcode,int length,uintptr_t target)
        {
            if(!Matches(va,opcode)) return false;
            int opcodeBytes=0; for(const char* p=opcode;*p;++p) if(*p!=' ') ++opcodeBytes;
            opcodeBytes/=2;
            int32_t disp=0; uint8_t b=0;
            for(int i=0;i<4;i++){ if(!Byte(At(va)+opcodeBytes+i,b)) return false; disp|=int32_t(b)<<(8*i); }
            return va+length+disp==target;
        }
        // The call (E8 rel32) at va goes to target.
        bool CallsTo(uintptr_t va,uintptr_t target) { return RipTargets(va,"E8",5,target); }
    }
    // Is the engine's package loader busy? Static analysis 2026-11-11: the
    // zen loader FAsyncLoadingThread2 (constructor 0x144671e28, which also
    // allocates the TLS slot OnGameThread reads) is created by 0x14467796c,
    // which stores its IAsyncPackageLoader interface (object +8, vtable
    // 0x145de95e0) in the global 0x149145d30 (GPackageLoader). Slot 17 of that
    // vtable, 0x140872dec, is IsAsyncLoadingPackages: the queued-packages
    // counter (+0x208) or the in-flight counter (+0x20c) is non-zero, both read
    // atomically (slots 11 and 12 read them alone; slot 14 reads the suspended
    // byte +0x11). The creator's loads and store of the global, the vtable slot
    // and the function's bytes are checked before first use; any difference
    // leaves the check off and work never waits for it.
    namespace Loader
    {
        // Per game build (GameBuildId). Epic 1.005 found offline 2026-11-13: same code bytes, Creator's
        // instructions at the same offsets, slot 17 of the moved vtable pointing at the moved function.
        struct Addresses { uintptr_t global, vtable, isLoadingPackages, creator; };
        constexpr Addresses Builds[]={
            {0x149145d30,0x145de95e0,0x140872dec,0x14467796c},   // steam-2025-01
            {0x14907beb0,0x145d23438,0x1407956f8,0x1444d3d98},   // epic-1.005
        };
        uintptr_t Global=0, Vtable=0, IsLoadingPackages=0, Creator=0;
        constexpr int Slot=17;
        int state=0;   // 0 unchecked, 1 verified, -1 unverified
        bool Verify()
        {
            if(state) return state==1;
            uint64_t slot=0;
            const int build=GameBuild();
            if(build>=0){ Global=Builds[build].global; Vtable=Builds[build].vtable; IsLoadingPackages=Builds[build].isLoadingPackages; Creator=Builds[build].creator; }
            const bool ok=build>=0
                && Code::Matches(IsLoadingPackages,"33 D2 33 C0 F0 0F B1 91 08 02 00 00 75 0C 33 C0 F0 0F B1 91 0C 02 00 00 74 02 B2 01 8A C2 C3")
                && Code::RipTargets(Creator+0x55,"48 8B 0D",7,Global)    // mov rcx,[GPackageLoader]
                && Code::RipTargets(Creator+0x67,"48 89 15",7,Global)    // mov [GPackageLoader],rdx
                && Code::Qword(Code::At(Vtable+Slot*8),slot) && slot==Code::At(IsLoadingPackages);
            state=ok?1:-1;
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<(ok?"loader_check_ready\n":"loader_check_unverified_unknown_build\n");
            return ok;
        }
        // The loader's interface object, once its vtable is the verified one; else 0.
        uintptr_t Object()
        {
            uint64_t p=0, vtable=0;
            if(!Verify() || !Code::Qword(Code::At(Global),p) || !p || !Code::Qword(p,vtable) || vtable!=Code::At(Vtable)) return 0;
            return uintptr_t(p);
        }
        bool CallBusy(uintptr_t p,bool& out)
        {
            __try { out=reinterpret_cast<bool(__fastcall*)(void*)>(Code::At(IsLoadingPackages))(reinterpret_cast<void*>(p)); return true; }
            __except(1) { return false; }
        }
        // True while packages are queued or in flight; false when idle or unverified.
        bool Busy()
        {
            const uintptr_t p=Object();
            bool busy=false;
            return p && CallBusy(p,busy) && busy;
        }
        bool ReadCounters(uintptr_t p,int32_t& queued,int32_t& inFlight,uint8_t& suspended)
        {
            __try {
                queued=*reinterpret_cast<volatile const int32_t*>(p+0x208);
                inFlight=*reinterpret_cast<volatile const int32_t*>(p+0x20c);
                suspended=*reinterpret_cast<volatile const uint8_t*>(p+0x11);
                return true;
            } __except(1) { return false; }
        }
        bool Counters(int32_t& queued,int32_t& inFlight,uint8_t& suspended)
        {
            const uintptr_t p=Object();
            return p && ReadCounters(p,queued,inFlight,suspended);
        }
    }
    // Each request names one level: Junon town's battle navigation (it
    // holds Roche's arena battle setup here, but the open world never
    // streams it), then our owned arena plan, each ServerBuild first.
    struct Level { const wchar_t* tag; const wchar_t* path; const wchar_t* leaf; const wchar_t* ack; const char* event; };
    const Level levels[]={
            {STR("ModJunonColosseum_LoadJunonBtlNavServerBuild"),STR("/Game/Level/Game/Field/1350-JNONT/Layout/1350-JNONT_Btl_Navigation_Mod_ServerBuild"),
             STR("1350-JNONT_Btl_Navigation_Mod_ServerBuild"),STR("ModJunonBtlNavServerBuildAccepted_"),"junon_navigation_serverbuild_request_"},
            {STR("ModJunonColosseum_LoadJunonBtlNav"),STR("/Game/Level/Game/Field/1350-JNONT/Layout/1350-JNONT_Btl_Navigation_Mod"),
             STR("1350-JNONT_Btl_Navigation_Mod"),STR("ModJunonBtlNavAccepted_"),"junon_navigation_request_"},
            {STR("ModJunonColosseum_LoadOwnedServerBuild"),STR("/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild"),
             STR("1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild"),STR("ModJunonServerBuildAccepted_"),"owned_arena_serverbuild_request_"},
            {STR("ModJunonColosseum_LoadOwnedPlan"),STR("/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum"),
             STR("1300-JUNOA_BattlePlan_ModJunonColosseum"),STR("ModJunonPlanAccepted_"),"owned_arena_plan_request_"},
    };
    constexpr auto BoardMeshTag = STR("ModJunonColosseum_LoadBoardMesh");
    constexpr auto BoardMeshAck = STR("ModJunonBoardMeshLoaded_");
    // Off the game thread a request is queued (marker renamed with this prefix)
    // and served by the next game-thread ProcessEvent; a queued request that
    // then fails is renamed with the refused prefix so Lua stops waiting.
    constexpr auto QueuedPrefix = STR("ModJunonQueued_");
    constexpr auto RefusedPrefix = STR("ModJunonRefused_");
    void Event(const char* event,const char* what)
    {
        std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<event<<what<<"\n";
    }
    bool RenameMarker(RC::Unreal::UObject* object,const std::wstring& name)
    {
        using namespace RC::Unreal;
        auto flags=ERenameFlags(REN_ForceNoResetLoaders | REN_NonTransactional | REN_DontCreateRedirectors);
        return object->Rename(name.c_str(),nullptr,flags);
    }
    // A request marker: a StaticMeshActor whose name starts with prefix and
    // that carries exactly one tag (returned).
    bool MarkerTag(RC::Unreal::UObject* object,const wchar_t* prefix,std::wstring& tag)
    {
        using namespace RC::Unreal;
        if(!object || !object->GetClassPrivate() || object->GetClassPrivate()->GetName()!=STR("StaticMeshActor") ||
           !object->GetName().starts_with(prefix))return false;
        auto* tags=object->GetValuePtrByPropertyNameInChain<TArray<FName>>(STR("Tags"));
        if(!tags || tags->Num()!=1)return false;
        tag=(*tags)[0].ToString();
        return true;
    }
    const Level* LevelFor(const std::wstring& tag)
    {
        for(const auto& candidate:levels) if(tag==candidate.tag) return &candidate;
        return nullptr;
    }
    bool InFoyerBox(RC::Unreal::UObject* object)
    {
        const auto p=static_cast<RC::Unreal::AActor*>(object)->K2_GetActorLocation();
        return p.X()>-128000 && p.X()<-116000 && p.Y()>31500 && p.Y()<39000 && p.Z()>6000 && p.Z()<6500;
    }
    // Requests made off the game thread (2026-11-10: ~50 deferrals, a 20 s
    // wait for the board, because most Lua ticks land on workers) are queued
    // and served later on the game thread (AtGameThreadCall). The stored marker
    // pointer is used only after the object array confirms its slot still
    // holds that same reachable object; the marker's name, tag and place are
    // then checked again, so a marker Lua untagged or replaced is not served.
    //
    // Live 2026-11-10 20:55 (0.9.12): served on the next game-thread call of
    // any function, LoadLevelInstance succeeded and returned a stream, but the
    // ServerBuild stream then stayed pending (not loaded, should be loaded) for
    // minutes and the board never came. That call can sit inside engine work:
    // level streaming's own update, async-load completion callbacks, garbage
    // collection, world teardown or travel. A streaming level added there can
    // be missed by the update that is iterating, or its package request lost.
    // So a queued request is now served only at a safe point (SafePoint), at
    // most one per frame, and one that waits longer than Expiry is answered
    // ModJunonDeferred_: Lua then asks again on a later tick, as before the
    // queue. Since 2026-11-11 a request made on the game thread is queued too
    // (QueueRequest), and the queue waits while the package loader is busy, at
    // most FrameWork::MaxDefer.
    namespace Queue
    {
        struct Entry { RC::Unreal::UObject* marker; int32_t index; const Level* level; ULONGLONG at; }; // level null: board mesh
        // ms. Never served later than this, and answered Deferred at about this
        // age: Lua's own give-up (battle_plan QUEUE_TIMEOUT, foyer
        // MESH_QUEUE_TIMEOUT, 6 s) comes later, so it cannot race a late serve.
        constexpr ULONGLONG Expiry=3000;
        SRWLOCK lock=SRWLOCK_INIT;
        std::vector<Entry> entries;
        std::atomic<bool> any{false};
        // A newer request for the same level (or the board mesh) replaces a
        // queued one: one queued load per level, never two.
        bool Add(RC::Unreal::UObject* marker,const Level* level,bool& superseded)
        {
            int32_t index=-1;
            try { index=marker->GetInternalIndex(); } catch(...) { return false; }
            if(index<0) return false;
            AcquireSRWLockExclusive(&lock);
            const auto before=entries.size();
            entries.erase(std::remove_if(entries.begin(),entries.end(),[&](const Entry& e){ return e.level==level; }),entries.end());
            superseded=entries.size()!=before;
            const bool room=entries.size()<16;
            if(room) entries.push_back({marker,index,level,GetTickCount64()});
            any.store(!entries.empty(),std::memory_order_release);
            ReleaseSRWLockExclusive(&lock);
            return room;
        }
        // The oldest entry still young enough to serve and at least minAge ms
        // old (one per call; minAge holds requests back while the loader is busy).
        bool TakeOne(Entry& out,ULONGLONG minAge)
        {
            const auto now=GetTickCount64();
            bool found=false;
            AcquireSRWLockExclusive(&lock);
            for(auto it=entries.begin();it!=entries.end();++it){
                if(now-it->at>Expiry || now-it->at<minAge) continue;
                out=*it; entries.erase(it); found=true; break;
            }
            any.store(!entries.empty(),std::memory_order_release);
            ReleaseSRWLockExclusive(&lock);
            return found;
        }
        // Entries older than Expiry, removed: each entry leaves the queue once,
        // either served (TakeOne) or expired (here), never both.
        std::vector<Entry> TakeExpired()
        {
            const auto now=GetTickCount64();
            std::vector<Entry> out;
            AcquireSRWLockExclusive(&lock);
            for(auto it=entries.begin();it!=entries.end();){
                if(now-it->at>Expiry){ out.push_back(*it); it=entries.erase(it); } else ++it;
            }
            any.store(!entries.empty(),std::memory_order_release);
            ReleaseSRWLockExclusive(&lock);
            return out;
        }
        RC::Unreal::UObject* Alive(const Entry& e)
        {
            RC::Unreal::UObject* found=nullptr;
            // Visits exactly slot e.index; unreachable objects are skipped.
            RC::Unreal::UObjectGlobals::ForEachUObjectInRange(e.index,e.index,[&](RC::Unreal::UObject* object,int32_t,int32_t){
                if(object==e.marker) found=object;
                return RC::LoopAction::Break;
            });
            return found;
        }
        // The entry's marker if it is still exactly the queued request.
        RC::Unreal::UObject* Marker(const Entry& e)
        {
            std::wstring tag;
            auto* marker=Alive(e);
            if(marker && MarkerTag(marker,QueuedPrefix,tag) && (e.level ? LevelFor(tag)==e.level : tag==BoardMeshTag) && InFoyerBox(marker))
                return marker;
            return nullptr;
        }
    }
    // Where a queued request is served: the ProcessEvent of a Blueprint tick
    // event (any class's ReceiveTick: actors, components, AI tasks) or of a
    // camera modifier's BlueprintModifyCamera, on the game thread. UE4SS 3.0.1
    // offers no engine-tick hook here (its AActor::Tick hook is never enabled:
    // bHookAActorTick is not read from the settings), so these two per-frame
    // gameplay events stand in for one. Both run only inside UWorld::Tick's
    // gameplay phase: actor/component ticks run inside the tick groups, and
    // the camera managers update right after them, after every actor ticked.
    // Neither runs inside level streaming's update, async-load callbacks,
    // garbage collection (between frames), world teardown or travel (no world
    // ticks then). That is where Blueprints themselves call LoadLevelInstance;
    // the new stream joins the world's list and the next streaming update
    // requests its package. Probe 2026-11-09: in a fight, ReceiveTick and
    // BlueprintModifyCamera each ran about 28 times a second. Functions are
    // matched by name (an override's UFunction differs from Actor's own),
    // reading the comparison index as InfusionSkills::Event does.
    namespace SafePoint
    {
        uint32_t receiveTick=0, modifyCamera=0;
        void Init()
        {
            receiveTick=RC::Unreal::FName(STR("ReceiveTick"),RC::Unreal::FNAME_Find).GetComparisonIndex();
            modifyCamera=RC::Unreal::FName(STR("BlueprintModifyCamera"),RC::Unreal::FNAME_Find).GetComparisonIndex();
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)
                <<"queue_safe_point_ready receive_tick="<<(receiveTick?1:0)<<" camera_update="<<(modifyCamera?1:0)<<"\n";
        }
        const char* Kind(RC::Unreal::UFunction* function)
        {
            if(!function) return nullptr;
            const uint32_t name=*reinterpret_cast<const uint32_t*>(reinterpret_cast<uintptr_t>(function)+0x18);
            if(receiveTick && name==receiveTick) return "receive_tick";
            if(modifyCamera && name==modifyCamera) return "camera_update";
            return nullptr;
        }
        // At most one serve per frame: after a serve the gate stays shut until
        // the same object's same event comes round again (it ticks once a
        // frame), or 250 ms if that object stopped ticking. Game thread only.
        RC::Unreal::UObject* gateObject=nullptr;
        RC::Unreal::UFunction* gateFunction=nullptr;
        ULONGLONG gateAt=0;
        bool shut=false;
        bool Open(RC::Unreal::UObject* object,RC::Unreal::UFunction* function)
        {
            if(!shut) return true;
            if((object==gateObject && function==gateFunction) || GetTickCount64()-gateAt>250){ shut=false; return true; }
            return false;
        }
        void Close(RC::Unreal::UObject* object,RC::Unreal::UFunction* function)
        {
            shut=true; gateObject=object; gateFunction=function; gateAt=GetTickCount64();
        }
    }
    // A level we loaded moments ago is not loaded again (2026-11-10: guard
    // against Lua giving up on a queued request and asking again while the
    // serve was already under way). Such a request is acknowledged without a
    // second LoadLevelInstance; Lua finds the stream by its package name.
    // Lua's stuck-stream retry comes 20 s later, well outside the window.
    namespace Recent
    {
        constexpr ULONGLONG Window=5000;  // ms
        std::atomic<ULONGLONG> loadedAt[std::size(levels)]{};
        size_t Index(const Level* level) { return size_t(level-levels); }
        bool Duplicate(const Level* level)
        {
            const auto at=loadedAt[Index(level)].load();
            return at && GetTickCount64()-at<Window;
        }
        void Loaded(const Level* level) { loadedAt[Index(level)].store(GetTickCount64()); }
    }
    // Every request is queued and served at a safe point (FrameWork), one made
    // on the game thread too (2026-11-11): the Lua tick runs inside whichever
    // ProcessEvent UE4SS drains its queue from, the same arbitrary context
    // 14b38d2 moved the off-thread requests away from (a load there can sit
    // inside level streaming's update or an async-load callback). Lua already
    // keeps a queued marker and collects the answer a tick later (battle_plan
    // collect, foyer check_queued_mesh). The old Deferred answer (Lua asks
    // again on a later tick) only if it cannot be queued.
    void QueueRequest(RC::Unreal::UObject* object,const Level* level,const char* event,bool gameThread)
    {
        const auto original=object->GetName();
        bool queued=false, superseded=false;
        try { queued=RenameMarker(object,QueuedPrefix+original) && Queue::Add(object,level,superseded); } catch(...) { queued=false; }
        if(!queued){
            try { RenameMarker(object,STR("ModJunonDeferred_")+original); } catch(...) {}
        }
        if(superseded) Event(event,"queued_superseded_older_request");
        Event(event,queued?(gameThread?"queued_for_safe_point":"queued_off_game_thread"):(gameThread?"deferred_on_game_thread":"deferred_off_game_thread"));
    }
    void RequestOwnedLevel(RC::Unreal::UObject* object)
    {
        std::wstring tag;
        if(!MarkerTag(object,STR("StaticMeshActor_"),tag))return;
        const Level* level=LevelFor(tag);
        if(!level)return;
        if(!InFoyerBox(object))return;
        QueueRequest(object,level,level->event,OnGameThread());
    }
    // The board borrows a native quest-board mesh. Streaming only brings it in
    // when Cloud arrives from outside, so a save made in the foyer reloads
    // without it. Load exactly that mesh by package path; the asset registry
    // does not list it, so UE4SS LoadAsset cannot.
    constexpr auto BoardMeshPath = STR("/Game/Environment/Interior/Model/Quest_Board_04A.Quest_Board_04A");
    // Load one object synchronously by its object path ("/Game/Pkg.Obj", or a
    // class "/Game/Pkg.Obj_C") with KismetSystemLibrary's reflected
    // LoadAsset_Blocking. Game thread, at a safe point. Every offset and size
    // comes from reflected metadata; the trace gets one line per step.
    RC::Unreal::UObject* LoadAssetPath(const wchar_t* path,std::ofstream& trace)
    {
        using namespace RC::Unreal;
        auto* api=UObjectGlobals::StaticFindObject<UObject*>(nullptr,nullptr,STR("/Script/Engine.Default__KismetSystemLibrary"));
        auto* fn=UObjectGlobals::StaticFindObject<UFunction*>(nullptr,nullptr,STR("/Script/Engine.KismetSystemLibrary:LoadAsset_Blocking"));
        auto refuse=[&](const char* reason)->UObject*{trace<<"refused\t"<<reason<<"\n";return nullptr;};
        if(!api || !fn)return refuse("function_or_default_missing");
        trace<<"method\tLoadAsset_Blocking\nnum_params\t"<<int(fn->GetNumParms())<<"\nproperties_size\t"<<fn->GetPropertiesSize()<<"\nsizeof_soft_ptr\t"<<sizeof(FSoftObjectPtr)<<"\n";
        if(fn->GetNumParms()!=2 || fn->GetPropertiesSize()<8 || fn->GetPropertiesSize()>256)return refuse("unexpected_parameter_block");
        struct Parameters {
            std::vector<uint8_t> bytes;
            std::vector<FProperty*> fields;
            ~Parameters(){for(auto it=fields.rbegin();it!=fields.rend();++it)(*it)->DestroyValue_InContainer(bytes.data());}
        } params{std::vector<uint8_t>(fn->GetPropertiesSize()),{}};
        FProperty *asset=nullptr,*result=nullptr;
        for(auto* field:fn->ForEachProperty()){
            if(!field->HasAnyPropertyFlags(CPF_Parm))continue;
            const auto fieldName=field->GetName();
            trace<<"field\t"<<std::string(fieldName.begin(),fieldName.end())<<"\t"<<field->GetOffset_Internal()<<"\t"<<field->GetElementSize()
                 <<"\tsoft="<<field->IsA<FSoftObjectProperty>()<<"\tobject="<<field->IsA<FObjectProperty>()<<"\n";
            if(field->GetArrayDim()!=1 || field->GetOffset_Internal()<0 || field->GetElementSize()<1 ||
               field->GetOffset_Internal()+field->GetElementSize()>fn->GetPropertiesSize()) return refuse("field_outside_parameter_block");
            field->InitializeValue_InContainer(params.bytes.data());params.fields.push_back(field);
            const auto n=field->GetName();
            if(n==STR("Asset"))asset=field;
            else if(n==STR("ReturnValue"))result=field;
            else return refuse("unknown_parameter");
        }
        if(!asset || !result || !asset->IsA<FSoftObjectProperty>() || !result->IsA<FObjectProperty>() ||
           asset->GetElementSize()!=sizeof(FSoftObjectPtr) || result->GetElementSize()!=sizeof(UObject*)) return refuse("parameter_type_or_size");
        auto* soft=asset->ContainerPtrToValuePtr<FSoftObjectPtr>(params.bytes.data());
        soft->ObjectID.AssetPathName=FName(path,FNAME_Add);
        api->ProcessEvent(fn,params.bytes.data());
        auto* loaded=*result->ContainerPtrToValuePtr<UObject*>(params.bytes.data());
        trace<<"native_dispatched\t1\nreturned\t"<<(loaded!=nullptr)<<"\n";
        return loaded;
    }
    bool LoadBoardMesh()
    {
        std::ofstream trace(Dev("junon-native-board-mesh.tsv"));
        auto* loaded=LoadAssetPath(BoardMeshPath,trace);
        const bool mesh=loaded && loaded->GetClassPrivate() && loaded->GetClassPrivate()->GetName()==STR("StaticMesh");
        trace<<"static_mesh\t"<<mesh<<"\n";
        return mesh;
    }
    void RequestBoardMesh(RC::Unreal::UObject* object)
    {
        std::wstring tag;
        if(!MarkerTag(object,STR("StaticMeshActor_"),tag) || tag!=BoardMeshTag)return;
        if(!InFoyerBox(object))return;
        QueueRequest(object,nullptr,"board_mesh_request_",OnGameThread());
    }
    // Game thread only: serve one queued request exactly as the synchronous
    // paths above would, with the marker as world context, and acknowledge by
    // the same rename (original name after the accepted prefix).
    void ServeEntry(const Queue::Entry& e,const char* kind,RC::Unreal::UFunction* via)
    {
        using namespace RC::Unreal;
        const char* event=e.level?e.level->event:"board_mesh_request_";
        UObject* marker=nullptr;
        try { marker=Queue::Marker(e); } catch(...) { marker=nullptr; }
        if(!marker){ Event(event,"queued_marker_gone"); return; }
        std::wstring original;
        try { original=marker->GetName().substr(std::wcslen(QueuedPrefix)); } catch(...) { return; }
        if(e.level && Recent::Duplicate(e.level)){
            bool acknowledged=false;
            try { acknowledged=RenameMarker(marker,e.level->ack+original); } catch(...) {}
            Event(event,acknowledged?"duplicate_acknowledged_without_load":"duplicate_refused");
            return;
        }
        bool accepted=false;
        try {
            const bool loaded=e.level ? LoadOwnedLevel(marker,e.level->path,e.level->leaf,e.level!=&levels[0]) : LoadBoardMesh();
            if(loaded && e.level) Recent::Loaded(e.level);
            if(loaded) accepted=RenameMarker(marker,(e.level ? std::wstring(e.level->ack) : std::wstring(BoardMeshAck))+original);
        } catch(const std::exception& error) {
            std::ofstream(Dev(e.level?"junon-native-plan-load.tsv":"junon-native-board-mesh.tsv"),std::ios::app)<<"cpp_exception\t"<<error.what()<<"\n";
        } catch(...) {}
        if(!accepted){
            try { RenameMarker(marker,RefusedPrefix+original); } catch(...) {}
        }
        std::string where;
        try { const auto name=via->GetFullName(); where.assign(name.begin(),name.end()); } catch(...) {}
        std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)
            <<event<<(accepted?"served_on_game_thread":"served_refused")<<"\t"<<kind<<"\t"<<(GetTickCount64()-e.at)<<"ms\t"<<where<<"\n";
    }
    // Requests not served within Queue::Expiry: answered Deferred, so Lua asks
    // again (and loads synchronously when its tick is on the game thread).
    void ExpireQueued()
    {
        using namespace RC::Unreal;
        for(const auto& e:Queue::TakeExpired()){
            const char* event=e.level?e.level->event:"board_mesh_request_";
            bool answered=false;
            try {
                if(auto* marker=Queue::Marker(e))
                    answered=RenameMarker(marker,STR("ModJunonDeferred_")+marker->GetName().substr(std::wcslen(QueuedPrefix)));
            } catch(...) { answered=false; }
            Event(event,answered?"queued_expired_deferred":"queued_expired_marker_gone");
        }
    }
    void RenameBoard(RC::Unreal::UObject* object)
    {
        bool ok = false;
        {
            if (object && object->GetClassPrivate() &&
                object->GetClassPrivate()->GetName() == STR("EndBulletinBoardPoint") &&
                object->GetName().starts_with(STR("EndBulletinBoardPoint_")))
            {
                auto* actor = static_cast<RC::Unreal::AActor*>(object);
                const auto location = actor->K2_GetActorLocation();
                auto* tags=object->GetValuePtrByPropertyNameInChain<RC::Unreal::TArray<RC::Unreal::FName>>(STR("Tags"));
                if (!tags || tags->Num()!=1) return;
                const auto requested=(*tags)[0].ToString();
                const bool foyer=location.X()>-128000 && location.X()<-116000 && location.Y()>31500 && location.Y()<39000 && location.Z()>6000 && location.Z()<6500;
                const bool under=location.X()>-90000 && location.X()<-70000 && location.Y()>70000 && location.Y()<100000 && location.Z()>0 && location.Z()<10000;
                const bool owned=(foyer && (requested==BoardName || requested==STR("oblMod_JunonColosseum_ExitTerminal"))) ||
                                 (under && requested==STR("oblMod_JunonColosseum_EntryGuard"));
                if (owned)
                {
                    auto flags = RC::Unreal::ERenameFlags(REN_ForceNoResetLoaders | REN_NonTransactional | REN_DontCreateRedirectors);
                    if (object->Rename(requested.c_str(), nullptr, RC::Unreal::ERenameFlags(flags | REN_Test)))
                        ok = object->Rename(requested.c_str(), nullptr, flags) && object->GetName() == requested;
                    std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app) << (ok ? "deferred_noticeboard_named\n" : "deferred_noticeboard_name_refused\n");
                }
            }
        }
    }

    // Opt-in diagnostic: while junon-probe.on exists in the dev.txt telemetry
    // folder, count every ProcessEvent function and append each 5 s window's
    // counts to junon-probe.tsv. It reads names only and calls nothing. The
    // flag file is looked for once every 4096 calls; off, it costs a counter.
    void Probe(RC::Unreal::UFunction* function)
    {
        using namespace RC::Unreal;
        static uint32_t calls=0;
        static bool on=false;
        static std::unordered_map<UFunction*,uint32_t> window;
        static auto last=std::chrono::steady_clock::now();
        if((++calls&4095)==0) on=DevFlag("junon-probe.on");
        if(!on){ if(!window.empty()) window.clear(); return; }
        ++window[function];
        const auto now=std::chrono::steady_clock::now();
        if(now-last<std::chrono::seconds(5))return;
        last=now;
        std::ofstream out(Dev("junon-probe.tsv"),std::ios::app);
        const auto stamp=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
        for(const auto& [fn,count]:window){
            const auto name=fn->GetFullName();
            std::string narrow; narrow.reserve(name.size());
            for(auto ch:name) narrow.push_back(ch<128?static_cast<char>(ch):'?');
            out<<stamp<<"\t"<<count<<"\t"<<narrow<<"\n";
        }
        window.clear();
    }

    // Opt-in diagnostic: while junon-colosseum-scan.on exists in the dev.txt
    // telemetry folder, a background thread finds the native colosseum battle sequence
    // and reports what its setup waits on (junon-colosseum-scan.tsv). Read
    // only. Offsets come from the executable's decompiled code (2026-11-09):
    // the battle sequence (vtable 0x145bf2fb0 at image base 0x140000000) holds
    // its manager at +8 and its setup sub-step at +0x298; setup waits for the
    // manager's current round (+0x78) entry (array +0x720, count +0x728) to
    // reach state 2 at +0xc, and for the byte behind the global 0x1492a03d0 to
    // be zero.
    namespace ColosseumScan
    {
        constexpr uintptr_t ImageBase=0x140000000, SequenceVtable=0x145bf2fb0, LoadFlagGlobal=0x1492a03d0;
        template<class T> bool Read(uintptr_t at,T& out)
        {
            MEMORY_BASIC_INFORMATION mbi{};
            if(!at || !VirtualQuery(reinterpret_cast<void*>(at),&mbi,sizeof(mbi)) || mbi.State!=MEM_COMMIT ||
               (mbi.Protect&(PAGE_NOACCESS|PAGE_GUARD)) || at+sizeof(T)>reinterpret_cast<uintptr_t>(mbi.BaseAddress)+mbi.RegionSize) return false;
            __try { out=*reinterpret_cast<const T*>(at); return true; } __except(1) { return false; }
        }
        // Plain loop (no C++ objects) so a page vanishing mid-scan is caught here.
        size_t FindQword(uintptr_t start,uintptr_t size,uintptr_t value,uintptr_t* hits,size_t max)
        {
            size_t n=0;
            __try {
                for(uintptr_t p=start;p+8<=start+size && n<max;p+=8)
                    if(*reinterpret_cast<const uintptr_t*>(p)==value) hits[n++]=p;
            } __except(1) {}
            return n;
        }
        void Hex(std::ofstream& out,uintptr_t at,int bytes)
        {
            for(int i=0;i<bytes;i+=8){ uint64_t q=0; if(Read(at+i,q)) out<<std::hex<<q<<std::dec<<" "; else out<<"? "; }
        }
        void ScanOnce()
        {
            const uintptr_t base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
            const uintptr_t vtable=SequenceVtable-ImageBase+base;
            std::ofstream out(Dev("junon-colosseum-scan.tsv"),std::ios::app);
            const auto stamp=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            out<<"scan\t"<<stamp<<"\tbase\t"<<std::hex<<base<<std::dec<<"\n";
            uintptr_t flagPtr=0; uint8_t flag=0xff;
            if(Read(LoadFlagGlobal-ImageBase+base,flagPtr) && flagPtr) Read(flagPtr,flag);
            out<<"load_flag_ptr\t"<<std::hex<<flagPtr<<std::dec<<"\tvalue\t"<<int(flag)<<"\n";
            SYSTEM_INFO si{}; GetSystemInfo(&si);
            uintptr_t at=reinterpret_cast<uintptr_t>(si.lpMinimumApplicationAddress); int found=0;
            const uintptr_t end=reinterpret_cast<uintptr_t>(si.lpMaximumApplicationAddress);
            MEMORY_BASIC_INFORMATION mbi{};
            while(at<end && found<8 && VirtualQuery(reinterpret_cast<void*>(at),&mbi,sizeof(mbi))){
                const uintptr_t start=reinterpret_cast<uintptr_t>(mbi.BaseAddress), size=mbi.RegionSize;
                if(mbi.State==MEM_COMMIT && mbi.Type==MEM_PRIVATE && (mbi.Protect==PAGE_READWRITE)){
                    uintptr_t hits[8]; const size_t n=FindQword(start,size,vtable,hits,8-found);
                    for(size_t h=0;h<n;h++){
                            const uintptr_t p=hits[h];
                            ++found; uintptr_t manager=0; int sub=-1,first=-1,round=-1,count=-1; uintptr_t entries=0;
                            Read(p+8,manager); Read(p+0x298,sub); Read(p+0x530,first);
                            Read(manager+0x78,round); Read(manager+0x720,entries); Read(manager+0x728,count);
                            out<<"sequence\t"<<std::hex<<p<<"\tmanager\t"<<manager<<std::dec<<"\tsub\t"<<sub<<"\tfirst\t"<<first
                               <<"\tround\t"<<round<<"\tentries\t"<<count<<"\n";
                            for(int i=0;i<count && i<12;i++){
                                uintptr_t e=0; int state=-1; Read(entries+i*8,e); Read(e+0xc,state);
                                out<<"entry\t"<<i<<"\t"<<std::hex<<e<<std::dec<<"\tstate\t"<<state<<"\tbytes\t"; Hex(out,e,0x40); out<<"\n";
                            }
                            out<<"manager_head\t"; Hex(out,manager,0x100); out<<"\n";
                            // The battle state finds its battle by the course's key (+0x288) and
                            // resolves the territory actor by FName (+0x1b0); +0x29c is the round count.
                            uintptr_t course=0; Read(manager+0x28,course);
                            out<<"course\t"<<std::hex<<course<<std::dec<<"\tsub_battle\t"; int sb=-1; Read(p+0x29c,sb); out<<sb<<"\tfields_1a0\t"; Hex(out,course+0x1a0,0x30);
                            out<<"\tfields_220\t"; Hex(out,course+0x220,0x30); out<<"\tfields_280\t"; Hex(out,course+0x280,0x28); out<<"\n";
                            uintptr_t key=0; Read(course+0x288,key); out<<"key_head\t"<<std::hex<<key<<std::dec<<"\t"; Hex(out,key,0x40); out<<"\n";
                            // Name the course's FName-looking fields (index below 4M, small number).
                            for(uintptr_t off=0x100; course && off<=0x2b0; off+=8){
                                uint64_t v=0; if(!Read(course+off,v)) continue;
                                const uint32_t index=uint32_t(v), number=uint32_t(v>>32);
                                if(index==0 || index>=0x400000 || number>=64) continue;
                                const auto name=RC::Unreal::FName(int64_t(v)).ToString();
                                std::string narrow; for(auto ch:name) narrow.push_back(ch<128?char(ch):'?');
                                out<<"course_name\t"<<std::hex<<off<<std::dec<<"\t"<<narrow<<"\n";
                            }
                    }
                }
                at=start+size;
            }
            // The battle registry (*(0x149001588)+0x278): a sparse array at +0x7b8 of
            // 0x18-byte entries whose record (+8) holds a weak pointer at +0x48 to a
            // battle; the battle lists its territory FNames at +0x178 (count +0x180)
            // and its state at +0xddcc. The colosseum waits for one listed first under
            // the course's TerritoryActorName.
            {
                uintptr_t g=0,r=0,data=0; int num=0;
                Read(0x149001588-ImageBase+base,g); Read(g+0x278,r); Read(r+0x7b8,data); Read(r+0x7c0,num);
                out<<"registry\t"<<std::hex<<r<<"\tdata\t"<<data<<std::dec<<"\tnum\t"<<num<<"\n";
                const int32_t total=RC::Unreal::UObjectArray::GetNumElements();
                for(int i=0;i<num && i<600;i++){
                    uintptr_t rec=0; int32_t index=-1,serial=0; uint64_t keyName=0;
                    if(!Read(data+i*0x18+8,rec) || !rec) continue;
                    Read(rec+0x48,index); Read(rec+0x4c,serial); Read(data+i*0x18,keyName);
                    // The entry key: the territory row it stands for (an FName).
                    std::string keyText;
                    if(uint32_t(keyName) && uint32_t(keyName)<0x400000 && (keyName>>32)<64){
                        for(auto ch:RC::Unreal::FName(int64_t(keyName)).ToString()) keyText.push_back(ch<128?char(ch):'?');
                    }
                    out<<"battle\t"<<i<<"\tkey\t"<<keyText<<"\tindex\t"<<index<<"\tserial\t"<<serial;
                    if(index>0 && index<total){
                        // The record's weak pointer has FWeakObjectPtr's layout (index, serial).
                        auto* object=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(rec+0x48)->Get();
                        if(object){
                            const uintptr_t o=reinterpret_cast<uintptr_t>(object);
                            uint8_t state=0xff; Read(o+0xddcc,state);
                            uintptr_t names=0; int count=0; Read(o+0x178,names); Read(o+0x180,count);
                            const auto full=object->GetFullName();
                            std::string narrow; for(auto ch:full) narrow.push_back(ch<128?char(ch):'?');
                            out<<"\tstate\t"<<int(state)<<"\tobject\t"<<narrow<<"\tnames";
                            for(int k=0;k<count && k<8;k++){
                                uint64_t v=0; if(!Read(names+k*8,v)) break;
                                const auto n=RC::Unreal::FName(int64_t(v)).ToString();
                                std::string nn; for(auto ch:n) nn.push_back(ch<128?char(ch):'?');
                                out<<"\t"<<nn;
                            }
                            // What the registry tick checks before it starts this territory's battle:
                            // record +0x10/+0x50; actor active +0xbe2c, type +0xbe2d, mode +0xddd0,
                            // spawn entries +0xd610, and the partner link +0xe0ac/+0xe0b0/+0xe0b8.
                            uintptr_t r10=0,e0b0=0; uint8_t r50=0,be2c=0,be2d=0; int32_t ddd0=0,d610=0,e0ac=0,e0b8=0,e0bc=0;
                            Read(rec+0x10,r10); Read(rec+0x50,r50); Read(o+0xbe2c,be2c); Read(o+0xbe2d,be2d); Read(o+0xddd0,ddd0);
                            Read(o+0xd610,d610); Read(o+0xe0ac,e0ac); Read(o+0xe0b0,e0b0); Read(o+0xe0b8,e0b8); Read(o+0xe0bc,e0bc);
                            out<<"\trec10\t"<<std::hex<<r10<<std::dec<<"\trec50\t"<<int(r50)<<"\tactive\t"<<int(be2c)<<"\ttype\t"<<int(be2d)
                               <<"\tddd0\t"<<ddd0<<"\tspawns\t"<<d610<<"\te0ac\t"<<e0ac<<"\te0b0\t"<<std::hex<<e0b0<<std::dec<<"\te0b8\t"<<e0b8<<"\te0bc\t"<<e0bc;
                            // Spawn entries (0xf0 bytes, at +0xd600 or inline +0xbf80): the
                            // round waits (FUN_14335376c) while any has state 2 or 5 at +0x10.
                            {
                                uintptr_t spawnData=0; Read(o+0xd600,spawnData); if(!spawnData) spawnData=o+0xbf80;
                                for(int k=0;k<d610 && k<8;k++){
                                    int32_t st=-1; Read(spawnData+k*0xf0+0x10,st);
                                    out<<"\tspawn"<<k<<"\t"<<st<<":"; Hex(out,spawnData+k*0xf0,0xf0);
                                    // Name the entry's FName-looking words.
                                    for(int w=0;w<0x60;w+=4){
                                        uint32_t index=0,number=0; Read(spawnData+k*0xf0+w,index); Read(spawnData+k*0xf0+w+4,number);
                                        if(index<0x1000 || index>=0x1000000 || number>=64) continue;
                                        std::string fn; for(auto ch:RC::Unreal::FName(int64_t(index)).ToString()) fn.push_back(ch<128?char(ch):'?');
                                        if(fn.size()>3 && fn!="None") out<<"|"<<std::hex<<w<<std::dec<<"="<<fn;
                                    }
                                }
                            }
                            std::string en;
                            if(uint32_t(e0b0) && uint32_t(e0b0)<0x1000000 && (e0b0>>32)<64){
                                for(auto ch:RC::Unreal::FName(int64_t(e0b0)).ToString()) en.push_back(ch<128?char(ch):'?');
                                out<<"\te0b0_name\t"<<en;
                            }
                            // Prepare's result: a weak pointer to the actor of the same name in
                            // the e0b0 level (FUN_142b0c4f4), which must be of a given class.
                            if(e0b8>0 && e0b8<total){
                                if(auto* partner=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(o+0xe0b8)->Get()){
                                    std::string pn; for(auto ch:partner->GetFullName()) pn.push_back(ch<128?char(ch):'?');
                                    out<<"\tpartner\t"<<pn;
                                }
                            }
                            // Ours never gets that far: Prepare returns early because the level
                            // registry (*(0x1492a0380)+0x88) has no entry for our ServerBuild.
                            // Look for the partner ourselves and, when asked, do Prepare's work.
                            if(e0ac!=-1 && count>0 && en.find("ModJunonColosseum_ServerBuild")!=std::string::npos){
                                uint64_t first=0; Read(names,first);
                                const std::string level=en.substr(en.rfind('/')+1)+":PersistentLevel.";
                                RC::Unreal::UObject* found=nullptr;
                                RC::Unreal::UObjectGlobals::ForEachUObject([&](RC::Unreal::UObject* candidate,int32_t,int32_t){
                                    // UObjectBase::NamePrivate sits at +0x18 (vtable, flags, index, class).
                                    if(candidate && candidate!=object && *reinterpret_cast<const uint64_t*>(reinterpret_cast<uintptr_t>(candidate)+0x18)==first){
                                        std::string cn; for(auto ch:candidate->GetFullName()) cn.push_back(ch<128?char(ch):'?');
                                        out<<"\tsame_name\t"<<cn;
                                        if(cn.find(level)!=std::string::npos) found=candidate;
                                    }
                                    return RC::LoopAction::Continue;
                                });
                                // ArenaReady (game thread) does the Prepare writes; this only reports.
                                out<<"\tpartner_found\t"<<(found?1:0);
                            }
                        }
                    }
                    out<<"\n";
                }
                // The character pop manager (*(0x149001588)+0x180, request entry 0x1410c41e8):
                // +0x1238 a set of pending spawn names (0x10-byte elements), +0x1288 a map of
                // requested asset FNames to reference counts (0x14-byte elements).
                {
                    uintptr_t pop=0; Read(g+0x180,pop);
                    auto name=[](uint64_t raw){ std::string s; if(uint32_t(raw) && uint32_t(raw)<0x1000000 && (raw>>32)<0x10000) for(auto ch:RC::Unreal::FName(int64_t(raw)).ToString()) s.push_back(ch<128?char(ch):'?'); return s; };
                    uintptr_t pend=0,assets=0; int npend=0,nassets=0;
                    Read(pop+0x1238,pend); Read(pop+0x1240,npend); Read(pop+0x1288,assets); Read(pop+0x1290,nassets);
                    out<<"pop_manager\t"<<std::hex<<pop<<std::dec<<"\tpending\t"<<npend<<"\tassets\t"<<nassets<<"\n";
                    for(int i=0;i<npend && i<256;i++){ uint64_t k=0; if(Read(pend+i*0x10,k) && k) out<<"pop_pending\t"<<i<<"\t"<<name(k)<<"\n"; }
                    // The pop "server" (pop+0x10): a map at +8 of spawn name -> record
                    // (0x18-byte elements, record pointer at +8; the record's +0x1a4 is a
                    // weak pointer to the spawned character). Dump records for our arena's
                    // spawns and a few spawned field mobs to compare their state.
                    uintptr_t server=0,sdata=0; int snum=0;
                    Read(pop+0x10,server); Read(server+8,sdata); Read(server+0x10,snum);
                    out<<"pop_server\t"<<std::hex<<server<<std::dec<<"\tnum\t"<<snum<<"\n";
                    int others=0;
                    for(int i=0;i<snum && i<4096;i++){
                        uint64_t k=0; uintptr_t rec=0;
                        if(!Read(sdata+i*0x18,k) || !k || !Read(sdata+i*0x18+8,rec) || !rec) continue;
                        const std::string n=name(k);
                        const bool ours=n.find("UCBattle")!=std::string::npos;
                        if(!ours && (n.rfind("mob",0)!=0 || ++others>4)) continue;
                        out<<"pop_record\t"<<n<<"\t"<<std::hex<<rec<<std::dec<<"\t"; Hex(out,rec,0x240); out<<"\n";
                    }
                    for(int i=0;i<nassets && i<2048;i++){
                        // TSet element: FName key, int count, then hash links; 8-byte aligned (0x18).
                        uint64_t k=0; int32_t c=0; if(!Read(assets+i*0x18,k) || !k) continue; Read(assets+i*0x18+8,c);
                        out<<"pop_asset\t"<<i<<"\t"<<name(k)<<"\t"<<c<<"\n";
                    }
                }
                // The map Prepare consults first (*(0x1492a0380)+0x88): entries of 0x18 bytes,
                // FName key at +0, value pointer at +8 whose byte at +0x10 must be set.
                uintptr_t m=0,mdata=0; int mnum=0;
                Read(0x1492a0380-ImageBase+base,m); Read(m+0x88,mdata); Read(m+0x90,mnum);
                out<<"prepare_map\t"<<std::hex<<m<<"\tdata\t"<<mdata<<std::dec<<"\tnum\t"<<mnum<<"\n";
                for(int i=0;i<mnum && i<4000;i++){
                    uint64_t k=0; uintptr_t val=0; uint8_t flag=0xff;
                    if(!Read(mdata+i*0x18,k)) break;
                    Read(mdata+i*0x18+8,val); if(val) Read(val+0x10,flag);
                    std::string kn;
                    if(uint32_t(k) && uint32_t(k)<0x1000000 && (k>>32)<64) for(auto ch:RC::Unreal::FName(int64_t(k)).ToString()) kn.push_back(ch<128?char(ch):'?');
                    out<<"prepare_entry\t"<<i<<"\t"<<kn<<"\tvalue\t"<<std::hex<<val<<std::dec<<"\tflag\t"<<int(flag);
                    if(val && (kn.find("ServerBuild")!=std::string::npos || kn.find("Btl_Navigation")!=std::string::npos || kn.find("BattlePlan")!=std::string::npos)){
                        out<<"\tvalue_bytes\t"; Hex(out,val,0x60);
                    }
                    out<<"\n";
                }
            }
            out<<"found\t"<<found<<"\n";
        }
        // One-shot: list loaded objects whose name contains any line of
        // junon-list-objects.on (then delete it) to junon-objects.tsv.
        void ListObjects()
        {
            const std::filesystem::path trigger=Dev("junon-list-objects.on");
            std::vector<std::string> wanted; { std::ifstream in(trigger); std::string line; while(std::getline(in,line)) if(!line.empty()) wanted.push_back(line); }
            std::filesystem::remove(trigger);
            std::ofstream out(Dev("junon-objects.tsv"),std::ios::app);
            out<<"list\t"<<std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count()<<"\n";
            RC::Unreal::UObjectGlobals::ForEachUObject([&](RC::Unreal::UObject* object,int32_t,int32_t){
                if(!object) return RC::LoopAction::Continue;
                const uint64_t raw=*reinterpret_cast<const uint64_t*>(reinterpret_cast<uintptr_t>(object)+0x18);
                std::string name; for(auto ch:RC::Unreal::FName(int64_t(raw)).ToString()) name.push_back(ch<128?char(ch):'?');
                for(const auto& w:wanted) if(name.find(w)!=std::string::npos){
                    std::string full; for(auto ch:object->GetFullName()) full.push_back(ch<128?char(ch):'?');
                    out<<full<<"\n"; break;
                }
                return RC::LoopAction::Continue;
            });
            out<<"end\n";
        }
        // The colosseum battle sequence (vtable 0x145bf2fb0) is a heap object,
        // not a UObject (hang 3's full dump: 0x7fee66b61c00), so the old object
        // search never found it ("sequence none"). While a stall switch exists
        // this thread scans committed private memory for its vtable (reads
        // only, as ScanOnce); readers check the vtable again before each use.
        std::atomic<uintptr_t> sequence{0};
        uintptr_t Sequence()
        {
            const uintptr_t p=sequence.load(std::memory_order_acquire);
            uint64_t vtable=0;
            return p && Code::Qword(p,vtable) && vtable==Code::At(SequenceVtable) ? p : 0;
        }
        uintptr_t FindSequence()
        {
            const uintptr_t vtable=Code::At(SequenceVtable);
            SYSTEM_INFO si{}; GetSystemInfo(&si);
            uintptr_t at=reinterpret_cast<uintptr_t>(si.lpMinimumApplicationAddress);
            const uintptr_t end=reinterpret_cast<uintptr_t>(si.lpMaximumApplicationAddress);
            MEMORY_BASIC_INFORMATION mbi{};
            while(at<end && VirtualQuery(reinterpret_cast<void*>(at),&mbi,sizeof(mbi))){
                const uintptr_t start=reinterpret_cast<uintptr_t>(mbi.BaseAddress), size=mbi.RegionSize;
                if(mbi.State==MEM_COMMIT && mbi.Type==MEM_PRIVATE && mbi.Protect==PAGE_READWRITE){
                    uintptr_t hits[8]; const size_t n=FindQword(start,size,vtable,hits,8);
                    for(size_t h=0;h<n;h++){
                        int32_t sub=-1;
                        if(Read(hits[h]+0x298,sub) && sub>=0 && sub<64) return hits[h];   // a live sequence's step
                    }
                }
                at=start+size;
            }
            return 0;
        }
        void Start()
        {
            if(GameBuild()!=SteamJan2025) return;   // dev diagnostics: old-build addresses only (not ported to 1.005)
            std::thread([]{
                ULONGLONG nextSearch=0;
                for(;;){
                    std::this_thread::sleep_for(std::chrono::seconds(3));
                    if(DevFlag("junon-list-objects.on")) ListObjects();
                    if(DevFlag("junon-colosseum-scan.on")) ScanOnce();
                    if((DevFlag("junon-stall.on") || DevFlag("junon-spawnstall.on")) && !Sequence() && GetTickCount64()>=nextSearch){
                        nextSearch=GetTickCount64()+15000;
                        sequence.store(FindSequence(),std::memory_order_release);
                    }
                }
            }).detach();
        }
    }

    // Our arena's territory is never "Prepared" by the game: Prepare
    // (0x140f9a484) needs the ServerBuild level in the game's level registry
    // (*(0x1492a0380)+0x88), and levels streamed with LevelStreamingDynamic are
    // never added. Without it the registry tick never starts the battle, so no
    // enemy spawns. On the game thread, about four times a second, find the
    // territory whose ServerBuild level (+0xe0b0) is ours and do Prepare's two
    // writes: link the same-named ServerBuild actor (+0xe0b8) with the game's own
    // weak-pointer setter (it allocates the serial Ready checks), then mark it
    // prepared (+0xe0ac = -1). Disabled unless the executable's bytes match the
    // build these offsets come from.
    namespace RoundShuffle { void Report(uint64_t key); void Tick(); }
    namespace ArenaReady
    {
        constexpr uintptr_t ImageBase=0x140000000;
        // Per game build (GameBuildId). Epic 1.005 found offline 2026-11-13 by matching Prepare and the
        // colosseum setup update instruction by instruction: the territory actor's fields (+0xe0ac/+0xe0b0/
        // +0xe0b8, +0xddcc) and the registry layout are unchanged; Prepare calls the weak-pointer setter at
        // +0xbf (old) / +0xbc (Epic).
        struct Addresses { uintptr_t readyCheck, prepareFn, weakAssignFn, fieldGlobal, prepareCallsWeakAssign; };
        constexpr Addresses Builds[]={
            {0x140eb95b8,0x140f9a484,0x1419b1394,0x149001588,0xbf},   // steam-2025-01
            {0x140bf5253,0x140e5e1c8,0x140834850,0x148f325f8,0xbc},   // epic-1.005
        };
        uintptr_t ReadyCheck=0, PrepareFn=0, WeakAssignFn=0, FieldGlobal=0;
        const wchar_t* Package=STR("/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild");
        const wchar_t* Partner=STR("/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild.1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild:PersistentLevel.UCBattle_TerritoryCmnActor");
        int state=0; // 0 unchecked, 1 enabled, -1 disabled
        // Game-thread reads: guarded by SEH only. ColosseumScan::Read's VirtualQuery
        // per read cost thousands of system calls a second here (frame hitches).
        template<class T> bool Peek(uintptr_t at,T& out)
        {
            if(at<0x10000) return false;
            __try { out=*reinterpret_cast<const T*>(at); return true; } __except(1) { return false; }
        }
        uintptr_t base=0;
        ULONGLONG preparedAt=0;   // last Prepare writes (for the stall log)
        void Log(const std::string& line)
        {
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app) << line << "\n";
        }
        bool Matches(uintptr_t va,std::initializer_list<uint8_t> bytes)
        {
            size_t i=0;
            for(uint8_t b:bytes){ uint8_t got=0; if(!Peek(va-ImageBase+base+i,got) || got!=b) return false; ++i; }
            return true;
        }
        // Names are compared as text once per distinct value, then cached
        // (an FName built here with FNAME_Find did not equal the stored one).
        std::unordered_map<uint64_t,bool> ours, roundKeys;
        bool IsOurs(uint64_t raw)
        {
            auto it=ours.find(raw);
            if(it!=ours.end()) return it->second;
            bool match=false;
            if(uint32_t(raw) && uint32_t(raw)<0x1000000 && (raw>>32)<0x10000) match=RC::Unreal::FName(int64_t(raw)).ToString()==std::wstring(Package);
            ours.emplace(raw,match);
            return match;
        }
        // Act only on a territory a course has armed for a round (registry key
        // terVR_COL30_*). Names ending in _100 carry the number 101 in the high
        // word, so numbers up to 0xffff count as valid (live 2026-11-10). Acting while our levels were still streaming in made two
        // loads in a row hang or crash (helper BZ, 2026-11-09).
        bool IsRoundKey(uint64_t raw)
        {
            auto it=roundKeys.find(raw);
            if(it!=roundKeys.end()) return it->second;
            bool match=false;
            if(uint32_t(raw) && uint32_t(raw)<0x1000000 && (raw>>32)<0x10000) match=RC::Unreal::FName(int64_t(raw)).ToString().rfind(STR("terVR_COL30_"),0)==0;
            roundKeys.emplace(raw,match);
            return match;
        }
        // The partner link (+0xe0b8, a weak pointer) still resolves.
        bool PartnerAlive(uintptr_t o)
        {
            int32_t index=-1;
            if(!Peek(o+0xe0b8,index) || index<=0 || index>=RC::Unreal::UObjectArray::GetNumElements()) return false;
            return reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(o+0xe0b8)->Get()!=nullptr;
        }
        // Our armed round's territory actor (a terVR_COL30_* registry key whose
        // territory's ServerBuild level is ours), or 0. Game thread.
        uintptr_t ArmedTerritory()
        {
            if(state!=1) return 0;
            uintptr_t g=0,r=0,data=0; int num=0;
            if(!Peek(FieldGlobal-ImageBase+base,g) || !Peek(g+0x278,r) || !r) return 0;
            Peek(r+0x7b8,data); Peek(r+0x7c0,num);
            const int32_t total=RC::Unreal::UObjectArray::GetNumElements();
            for(int i=0;i<num && i<2048;i++){
                uintptr_t rec=0; int32_t index=-1; uint64_t key=0, level=0;
                if(!Peek(data+i*0x18,key) || !key || !IsRoundKey(key)) continue;
                if(!Peek(data+i*0x18+8,rec) || !rec || !Peek(rec+0x48,index) || index<=0 || index>=total) continue;
                auto* object=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(rec+0x48)->Get();
                if(object && Peek(reinterpret_cast<uintptr_t>(object)+0xe0b0,level) && level && IsOurs(level)) return reinterpret_cast<uintptr_t>(object);
            }
            return 0;
        }
        // Game thread, at a safe point, every 250 ms (FrameWork).
        void Tick()
        {
            const auto now=std::chrono::steady_clock::now();
            if(state==0){
                base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
                // cmp dword [rcx+0xe0ac],-1 opens Ready; Prepare reads +0xe0b0 the same way,
                // and links the partner through the weak-pointer setter we call.
                const int build=GameBuild();
                bool ok=false;
                if(build>=0){
                    const auto& a=Builds[build];
                    ReadyCheck=a.readyCheck; PrepareFn=a.prepareFn; WeakAssignFn=a.weakAssignFn; FieldGlobal=a.fieldGlobal;
                    ok=Matches(ReadyCheck,{0x83,0xb9,0xac,0xe0,0x00,0x00,0xff}) && Code::CallsTo(PrepareFn+a.prepareCallsWeakAssign,WeakAssignFn);
                }
                state=ok?1:-1;
                Log(ok?"arena_ready_enabled":"arena_ready_disabled_unknown_build");
            }
            if(state!=1) return;
            uintptr_t g=0,r=0,data=0; int num=0;
            if(!Peek(FieldGlobal-ImageBase+base,g) || !Peek(g+0x278,r) || !r) return;
            Peek(r+0x7b8,data); Peek(r+0x7c0,num);
            auto& isOurs=IsOurs;
            auto& isRoundKey=IsRoundKey;
            const int32_t total=RC::Unreal::UObjectArray::GetNumElements();
            // Rounds whose EnemyTerritoryLevel row has UsePopTargetPoint (byte +0x14f of
            // the row the registry record holds at +0x30) place their enemies at named
            // points of the simulator's VR level (obl_VR_mu_01..13: the three Mu rounds).
            // Those names do not exist in our arena, so the round builder (0x14147337c)
            // gives every entry the placeholder location and nothing spawns. While one of
            // our courses runs, clear the flag on such rows so they use the normal spawn
            // lists; restore the rows once our course ends (the simulator still uses them).
            {
                static std::vector<uintptr_t> patched;
                static auto lastActive=std::chrono::steady_clock::time_point{};
                bool active=false;
                uint64_t activeKey=0;
                for(int i=0;i<num && i<2048 && !active;i++){
                    uintptr_t rec=0; int32_t index=-1; uint64_t key=0, level=0;
                    if(!Peek(data+i*0x18,key) || !key || !isRoundKey(key)) continue;
                    if(!Peek(data+i*0x18+8,rec) || !rec || !Peek(rec+0x48,index) || index<=0 || index>=total) continue;
                    auto* object=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(rec+0x48)->Get();
                    if(object && Peek(reinterpret_cast<uintptr_t>(object)+0xe0b0,level) && level && isOurs(level)){ active=true; activeKey=key; }
                }
                if(active) RoundShuffle::Report(activeKey); // the round being fought (for the Lua)
                if(active){
                    lastActive=now;
                    for(int i=0;i<num && i<2048;i++){
                        uintptr_t rec=0, row=0; uint64_t key=0; uint8_t use=0;
                        if(!Peek(data+i*0x18,key) || !key || !isRoundKey(key)) continue;
                        if(!Peek(data+i*0x18+8,rec) || !rec || !Peek(rec+0x30,row) || !row || !Peek(row+0x14f,use) || use!=1) continue;
                        *reinterpret_cast<uint8_t*>(row+0x14f)=0;
                        patched.push_back(row);
                        Log("arena_pop_target_points_cleared");
                    }
                }else if(!patched.empty() && now-lastActive>std::chrono::seconds(3)){
                    for(uintptr_t row:patched) *reinterpret_cast<uint8_t*>(row+0x14f)=1;
                    patched.clear();
                    Log("arena_pop_target_points_restored");
                }
            }
            for(int i=0;i<num && i<2048;i++){
                uintptr_t rec=0; int32_t index=-1; uint64_t key=0;
                if(!Peek(data+i*0x18,key) || !key || !isRoundKey(key)) continue;
                if(!Peek(data+i*0x18+8,rec) || !rec || !Peek(rec+0x48,index) || index<=0 || index>=total) continue;
                auto* object=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(rec+0x48)->Get();
                if(!object) continue;
                const uintptr_t o=reinterpret_cast<uintptr_t>(object);
                uint64_t level=0; int32_t prepared=0;
                if(!Peek(o+0xe0ac,prepared) || !Peek(o+0xe0b0,level) || !level || !isOurs(level)) continue;
                // Live 2026-11-11 a course stalled between rounds with no round
                // territory armed. A territory prepared earlier whose partner link
                // no longer resolves (our ServerBuild's actor went away, and came
                // back with the level) could never begin: link the partner again,
                // only while the territory is idle (+0xddcc 0 or 4, as Watch arms),
                // at most every 5 s. The prepared mark itself stays.
                const bool relink=prepared==-1;
                if(relink){
                    static auto lastRelink=std::chrono::steady_clock::time_point{};
                    uint8_t phase=0xff;
                    if(PartnerAlive(o) || !Peek(o+0xddcc,phase) || (phase!=0 && phase!=4) || now-lastRelink<std::chrono::seconds(5)) continue;
                    lastRelink=now;
                    Log("arena_ready_partner_lost");
                }
                auto* partner=RC::Unreal::UObjectGlobals::StaticFindObject<RC::Unreal::UObject*>(nullptr,nullptr,Partner);
                static auto lastSearch=std::chrono::steady_clock::time_point{};
                if(!partner && now-lastSearch>=std::chrono::seconds(5)){
                    lastSearch=now;
                    // Same name (UObjectBase::NamePrivate at +0x18) as the territory's
                    // first name, inside our ServerBuild level. Once per round start.
                    uintptr_t names=0; uint64_t first=0;
                    Peek(o+0x178,names); Peek(names,first);
                    const std::wstring wanted(Partner);
                    RC::Unreal::UObjectGlobals::ForEachUObject([&](RC::Unreal::UObject* candidate,int32_t,int32_t){
                        if(candidate && candidate!=object && *reinterpret_cast<const uint64_t*>(reinterpret_cast<uintptr_t>(candidate)+0x18)==first){
                            const auto full=candidate->GetFullName();
                            if(full.size()>=wanted.size() && full.compare(full.size()-wanted.size(),wanted.size(),wanted)==0){ partner=candidate; return RC::LoopAction::Break; }
                        }
                        return RC::LoopAction::Continue;
                    });
                    Log(partner?"arena_ready_partner_found_by_search":"arena_ready_partner_missing");
                }
                if(!partner){ continue; }
                using WeakAssign=void(*)(void*,void*);
                reinterpret_cast<WeakAssign>(WeakAssignFn-ImageBase+base)(reinterpret_cast<void*>(o+0xe0b8),partner);
                *reinterpret_cast<int32_t*>(o+0xe0ac)=-1;
                preparedAt=GetTickCount64();
                Log(relink?"arena_ready_relinked":"arena_ready_prepared");
            }
        }
    }

    // Curated random rounds (owner design 2026-11-09). The mod's Lua draws each
    // course's rounds for the next run and writes them to junon-rounds.req: per
    // course one line "@<colosseum row> <territory> ..." with the rounds the
    // shipped table holds, and one "<colosseum row> <territory> ..." with the new
    // draw. The game reads a course's rounds from the loaded colosseum table
    // (UEndDataObjectColosseum) when the course starts, so on the game thread the
    // helper overwrites each course's round names there, in place (the count
    // never changes), and acknowledges in junon-rounds.ack. It also reports the
    // current round's territory (the registry key ArenaReady acts on) in
    // junon-round.txt for the Lua.
    namespace RoundShuffle
    {
        std::string RequestPath() { return Shared("junon-rounds.req"); }
        std::string AckPath() { return Shared("junon-rounds.ack"); }
        std::string CurrentPath() { return Shared("junon-round.txt"); }
        template<class T> bool Peek(uintptr_t at,T& out)
        {
            if(at<0x10000) return false;
            __try { out=*reinterpret_cast<const T*>(at); return true; } __except(1) { return false; }
        }
        std::wstring Text(uint64_t raw)
        {
            if(!uint32_t(raw) || uint32_t(raw)>=0x1000000 || (raw>>32)>=0x10000) return {};
            return RC::Unreal::FName(int64_t(raw)).ToString();
        }
        std::unordered_map<std::wstring,uint64_t> names;     // territory name -> FName value (0: unknown)
        std::filesystem::file_time_type applied{};
        auto last=std::chrono::steady_clock::time_point{};
        uint64_t reported=0;
        void Ack(const std::string& line){ std::ofstream(AckPath(),std::ios::app) << line << "\n"; }
        // Live layout (2026-11-10): the table object (+0x38) points at a frozen
        // memory image, whose pointers are offsets ((offset << 1) | 1). Its row
        // map is a set of 20-byte records {row name, row index, hash links}, but
        // the rows' arrays are stored in a form not decoded here (a 142-entry
        // array of 0x30-byte entries holds three string arrays per row). So each
        // of our courses' round lists is found by its contents instead: the
        // request's "@" lines give the rounds the shipped table holds (each
        // slot's first candidate), and one pass over the image finds every such
        // 8-name sequence. The addresses are kept for the session (later draws
        // overwrite those names).
        std::unordered_map<std::wstring,uintptr_t> lists;   // colosseum row -> round list data
        uintptr_t image=0;
        constexpr uintptr_t ImageScan=16u<<20;
        uint64_t Name(const std::wstring& text)
        {
            auto it=names.find(text);
            if(it!=names.end()) return it->second;
            RC::Unreal::FName n(text.c_str(),RC::Unreal::FNAME_Find);
            uint64_t raw=0;
            std::memcpy(&raw,&n,sizeof(raw));
            // Names compare without case; the table keeps the first spelling seen.
            const auto back=Text(raw);
            if(back.size()!=text.size() || _wcsicmp(back.c_str(),text.c_str())!=0){
                std::ostringstream s; s<<std::hex<<"unknown_name "<<std::string(text.begin(),text.end())<<" raw="<<raw<<" back="<<std::string(back.begin(),back.end());
                Ack(s.str());
                raw=0;
            }
            names.emplace(text,raw);
            return raw;
        }
        uintptr_t Image()
        {
            if(image) return image;
            auto* table=RC::Unreal::UObjectGlobals::StaticFindObject<RC::Unreal::UObject*>(nullptr,nullptr,STR("/Game/DataObject/Resident/Colosseum.Colosseum"));
            uintptr_t at=0;
            if(table && Peek(reinterpret_cast<uintptr_t>(table)+0x38,at) && at>=0x10000) image=at;
            return image;
        }
        std::string Narrow(const std::wstring& text){ return std::string(text.begin(),text.end()); }
        // One pass over the whole image: each pattern's first address (8-aligned)
        // that no row found earlier holds, or absent. Two rows that would get the
        // same address (one list a prefix of the other) are both left out and
        // reported: no shuffle beats writing one course's draw into another's
        // list (live 2026-11-10, when six course pairs shipped the same list).
        std::unordered_map<std::wstring,uintptr_t> Find(const std::unordered_map<std::wstring,std::vector<uint64_t>>& patterns)
        {
            std::unordered_map<std::wstring,uintptr_t> out;
            std::unordered_map<std::wstring,int> hits;
            std::unordered_multimap<uint64_t,const std::pair<const std::wstring,std::vector<uint64_t>>*> first;
            std::vector<uint64_t> starts;
            for(auto& p:patterns) if(!p.second.empty()){ first.emplace(p.second[0],&p); starts.push_back(p.second[0]); }
            std::sort(starts.begin(),starts.end());
            std::unordered_map<uintptr_t,std::wstring> held;
            for(auto& [row,at]:lists) held[at]=row;
            for(uintptr_t at=image;at<image+ImageScan;at+=8){
                uint64_t w=0;
                if(!Peek(at,w)) break;   // the end of the mapped image
                if(!std::binary_search(starts.begin(),starts.end(),w) || held.count(at)) continue;
                auto range=first.equal_range(w);
                for(auto it=range.first;it!=range.second;++it){
                    const auto& [row,values]=*it->second;
                    bool same=true;
                    for(size_t i=1;i<values.size() && same;i++){ uint64_t x=0; same=Peek(at+i*8,x) && x==values[i]; }
                    if(!same) continue;
                    if(!hits[row]++) out[row]=at;
                }
            }
            std::unordered_map<uintptr_t,int> claims;
            for(auto& [row,at]:out) claims[at]++;
            for(auto it=out.begin();it!=out.end();){
                if(hits[it->first]>1) Ack("repeated "+Narrow(it->first)+" hits="+std::to_string(hits[it->first])+" (the first is used)");
                if(claims[it->second]>1){ Ack("ambiguous "+Narrow(it->first)+" shares its list (skipped)"); it=out.erase(it); }
                else ++it;
            }
            return out;
        }
        void Apply()
        {
            if(!Image()){ Ack("table_not_loaded"); return; }
            std::unordered_map<std::wstring,std::vector<uint64_t>> defaults, wanted;
            int unknown=0;
            std::wifstream in(RequestPath());
            std::wstring line;
            while(std::getline(in,line)){
                std::wistringstream words(line);
                std::wstring row, territory;
                words>>row;
                if(row.empty()) continue;
                const bool isDefault=row[0]==L'@';
                if(isDefault) row=row.substr(1);
                std::vector<uint64_t> values;
                while(words>>territory){ const uint64_t v=Name(territory); if(!v) unknown++; values.push_back(v); }
                (isDefault?defaults:wanted)[row]=values;
            }
            // Rows that ship the same list cannot be told apart by content: refuse
            // both (the Lua's data ships a unique list per course).
            std::unordered_map<std::wstring,bool> refused;
            for(auto& [a,va]:defaults) for(auto& [b,vb]:defaults)
                if(a<b && va==vb){ refused[a]=refused[b]=true; Ack("ambiguous "+Narrow(a)+" "+Narrow(b)+" ship the same list (skipped)"); }
            std::unordered_map<std::wstring,std::vector<uint64_t>> search;
            for(auto& [row,values]:defaults) if(!lists.count(row) && wanted.count(row) && !refused.count(row)) search[row]=values;
            if(!search.empty()) for(auto& [row,at]:Find(search)) lists[row]=at;
            std::unordered_map<uintptr_t,int> owners;
            for(auto& [row,at]:lists) owners[at]++;
            int ok=0, bad=0;
            for(auto& [row,values]:wanted){
                auto it=lists.find(row);
                const auto d=defaults.find(row);
                if(refused.count(row) || it==lists.end() || owners[it->second]>1 || d==defaults.end() || d->second.size()!=values.size()){ bad++; continue; }
                if(std::find(values.begin(),values.end(),uint64_t(0))!=values.end()){ bad++; continue; }
                const uintptr_t arr=it->second;
                const SIZE_T bytes=values.size()*8;
                DWORD old=0;
                // The table is a mapped file: make the page writable, copy-on-write if need be.
                if(!VirtualProtect(reinterpret_cast<void*>(arr),bytes,PAGE_READWRITE,&old) &&
                   !VirtualProtect(reinterpret_cast<void*>(arr),bytes,PAGE_WRITECOPY,&old)){ bad++; Ack("protect_failed "+std::to_string(GetLastError())); continue; }
                for(size_t i=0;i<values.size();i++) *reinterpret_cast<uint64_t*>(arr+i*8)=values[i];
                DWORD ignored=0; VirtualProtect(reinterpret_cast<void*>(arr),bytes,old,&ignored);
                ok++;
            }
            Ack("applied ok="+std::to_string(ok)+" bad="+std::to_string(bad)+" lists="+std::to_string(lists.size())+" unknown_names="+std::to_string(unknown));
        }
        // Game thread, at a safe point, once a second (FrameWork).
        void Tick()
        {
            std::error_code ec;
            const auto stamp=std::filesystem::last_write_time(RequestPath(),ec);
            if(!ec && stamp!=applied){ applied=stamp; Apply(); }
        }
        // Called by ArenaReady with the active round's registry key, about four
        // times a second while a round of ours is armed. A key seen again after a
        // gap (a later round on the same territory) is written again, so the
        // file's time always shows the latest round.
        auto reportedAt=std::chrono::steady_clock::time_point{};
        void Report(uint64_t key)
        {
            const auto now=std::chrono::steady_clock::now();
            const bool gap=now-reportedAt>std::chrono::seconds(3);
            reportedAt=now;
            if(key==reported && !gap) return;
            reported=key;
            const auto text=Text(key);
            std::ofstream out(CurrentPath(),std::ios::trunc);
            out << std::string(text.begin(),text.end());
        }
    }

    // ---- Stall diagnostics (development installs only; reads only) ----
    // Live 2026-11-10 two courses hung on an endless "Get Ready" between rounds.
    // While the Lua's watchdog keeps junon-stall.on in the telemetry folder (no
    // battle for 45 s in a course), log once a second to junon-stall.tsv what the
    // colosseum's own between-round checks wait for (static analysis of the
    // executable, image base 0x140000000; addresses below are virtual addresses):
    //  - RoundReady 0x14335376c: the field registry *(*(0x149001588)+0x278) entry
    //    for the course row's TerritoryActorName (UCBattle_TerritoryCmnActor;
    //    none: never ready) and every terVR_COL30_* round key; per territory
    //    +0xddcc (3: not ready; step 5 waits for 2), +0xddd0, +0xe0ac (-1:
    //    prepared), +0xe0b0 (its ServerBuild level: ours?), +0xe0b8 (partner set?)
    //    and its spawn entries (0x1436ab6fc: not ready while one is in state 2 or 5;
    //    count +0xd610, array +0xd600 or inline +0xbf80, 0xf0 each, state +0x10);
    //  - step 6, pop manager idle 0x140ccb41c: p=*(g+0x180), needs +0x28==0,
    //    +0x930<1 and +0x1140<1;
    //  - setup update 0x143334fd4: needs the byte *(0x1492a03d0)==0 and
    //    *(*(0x1492a0390)+0x39)==0;
    //  - the sequence object (vtable 0x145bf2fb0, battle update 0x143333688) sub
    //    steps +0x298/+0x29c: a heap object, found by ColosseumScan's thread;
    //  - when ArenaReady last prepared a territory;
    //  - every five seconds, our arena's objects by name (worlds, levels and
    //    territory actors of the plan and its ServerBuild, and whether the
    //    garbage collector has marked them unreachable). Live 2026-11-11 the old
    //    StaticFindObject lookups by package or object path said "not loaded"
    //    for everything (the partner's full path is never found even while it
    //    exists: ArenaReady finds it by search), so they are gone.
    // Registry keys without a territory are counted, not listed (455 lines a
    // second, 2026-11-11). Off unless ArenaReady verified this executable.
    // Hang 4 (2026-11-11 12:03, dump hang-c3r5-full.dmp): the sequence sat at
    // setup step +0x298=3, which waits (0x140bb52e0) for the first byte of the
    // object *(0x1492a03d0) (the party character swap manager: +0x151 a player
    // type, +0x29/+0x2a flags) to be 0; it was 2 because two party pack loads
    // (Yuffie's weapon and its avatar) never completed: pack entries at state 2,
    // their engine ids still pending, the zen loader at 75 packages in flight
    // with every loader and IO thread idle. The old "setup_byte" here read the
    // low byte of that pointer, not the byte it points to (always 0), so the
    // line now reads the gate itself, the loader's counters and, map-wide,
    // every pack entry stuck in loading (SpawnStall::StuckPacks).
    // Game thread, at a safe point, once a second (FrameWork).
    namespace SpawnStall { void StuckPacks(std::ofstream& out,long long stamp); }
    namespace Stall
    {
        using ArenaReady::Peek;
        constexpr uintptr_t FieldGlobal=0x149001588, SetupByte=0x1492a03d0, SetupObject=0x1492a0390;
        auto arenaAt=std::chrono::steady_clock::time_point{};
        bool on=false;
        std::unordered_map<uint64_t,std::wstring> keys;   // registry key -> text when it is one we log
        std::string Hex(uint64_t v){ std::ostringstream s; s<<std::hex<<v; return s.str(); }
        template<class T> std::string Field(uintptr_t at){ T v{}; return Peek(at,v) ? std::to_string(v) : std::string("?"); }
        std::string Narrow(const std::wstring& text){ std::string s; s.reserve(text.size()); for(auto ch:text) s.push_back(ch<128?char(ch):'?'); return s; }
        // A weak object pointer's target, after checking its object index.
        RC::Unreal::UObject* Weak(uintptr_t at)
        {
            int32_t index=-1;
            if(!Peek(at,index) || index<=0 || index>=RC::Unreal::UObjectArray::GetNumElements()) return nullptr;
            return reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(at)->Get();
        }
        const std::wstring& Key(uint64_t raw)
        {
            auto it=keys.find(raw);
            if(it!=keys.end()) return it->second;
            auto text=RoundShuffle::Text(raw);
            if(text.rfind(STR("terVR_COL30_"),0)!=0 && text!=STR("UCBattle_TerritoryCmnActor")) text.clear();
            return keys.emplace(raw,text).first->second;
        }
        // Our arena's objects by name: one pass over the object array comparing
        // name indices (UObjectBase::NamePrivate at +0x18, as SafePoint reads
        // them), full names only for the few hits. Territory actors count only
        // inside our levels (their full name says ModJunonColosseum).
        void Arena(std::ofstream& out,long long stamp)
        {
            using namespace RC::Unreal;
            const uint32_t plan=FName(STR("1300-JUNOA_BattlePlan_ModJunonColosseum"),FNAME_Find).GetComparisonIndex();
            const uint32_t build=FName(STR("1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild"),FNAME_Find).GetComparisonIndex();
            const uint32_t territory=FName(STR("UCBattle_TerritoryCmnActor"),FNAME_Find).GetComparisonIndex();
            std::vector<std::string> hits;
            int total=0;
            UObjectGlobals::ForEachUObject([&](UObject* object,int32_t,int32_t){
                if(!object) return RC::LoopAction::Continue;
                const uint32_t n=*reinterpret_cast<const uint32_t*>(reinterpret_cast<uintptr_t>(object)+0x18);
                if(!n || (n!=plan && n!=build && n!=territory)) return RC::LoopAction::Continue;
                std::string full; bool unreachable=false;
                try { full=Narrow(object->GetFullName()); unreachable=object->IsUnreachable(); } catch(...) { return RC::LoopAction::Continue; }
                if(n==territory && full.find("ModJunonColosseum")==std::string::npos) return RC::LoopAction::Continue;
                total++;
                if(hits.size()<16) hits.push_back(full+(unreachable?" [unreachable]":""));
                return RC::LoopAction::Continue;
            });
            out<<stamp<<"\tarena\tnames="<<(plan?1:0)<<(build?1:0)<<(territory?1:0)<<"\tobjects="<<total;
            for(const auto& h:hits) out<<"\t"<<h;
            out<<"\n";
        }
        void Tick()
        {
            if(GameBuild()!=SteamJan2025) return;   // dev diagnostics: old-build addresses only (not ported to 1.005)
            const auto now=std::chrono::steady_clock::now();
            const auto trigger=Dev("junon-stall.on");
            std::error_code ec;
            if(trigger.empty() || !std::filesystem::exists(trigger,ec)){ on=false; return; }
            if(ArenaReady::state!=1) return;
            std::ofstream out(Dev("junon-stall.tsv"),std::ios::app);
            const auto stamp=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            if(!on){ on=true; arenaAt={}; out<<stamp<<"\tstall_begin\n"; }
            uintptr_t g=0, pop=0, setup=0, r=0, data=0, gate=0; int32_t num=0;
            Peek(Code::At(FieldGlobal),g);
            out<<stamp<<"\tglobals\tpop";
            if(g && Peek(g+0x180,pop) && pop) out<<"\t+28="<<Hex([&]{ uint64_t v=0; Peek(pop+0x28,v); return v; }())<<"\t+930="<<Field<int32_t>(pop+0x930)<<"\t+1140="<<Field<int32_t>(pop+0x1140);
            else out<<"\tnone";
            // Step 3 waits while the gate's first byte is not 0 (no object: open).
            out<<"\tswap_gate="<<(!Peek(Code::At(SetupByte),gate) ? std::string("?") : !gate ? std::string("none")
                : Field<uint8_t>(gate)+"/+29="+Field<uint8_t>(gate+0x29)+"/+151="+Field<uint8_t>(gate+0x151));
            {
                int32_t queued=-1, inFlight=-1; uint8_t suspended=0xff;
                if(Loader::Counters(queued,inFlight,suspended)) out<<"\tloader="<<queued<<"/"<<inFlight<<"/"<<int(suspended);
                else out<<"\tloader=unverified";
            }
            out<<"\tsetup+39="<<(Peek(Code::At(SetupObject),setup) && setup ? Field<uint8_t>(setup+0x39) : std::string("none"));
            const uintptr_t sequence=ColosseumScan::Sequence();
            out<<"\tsequence"<<(sequence ? "\t"+Hex(sequence)+"\t+298="+Field<int32_t>(sequence+0x298)+"\t+29c="+Field<int32_t>(sequence+0x29c) : std::string("\tnot_found_yet"));
            const ULONGLONG prepared=ArenaReady::preparedAt;
            out<<"\tarena_ready_prepared_s_ago="<<(prepared ? std::to_string((GetTickCount64()-prepared)/1000) : std::string("never"));
            const bool registry=g && Peek(g+0x278,r) && r;
            if(registry){ Peek(r+0x7b8,data); Peek(r+0x7c0,num); }
            out<<"\tregistry="<<(registry ? std::to_string(num) : std::string("none"))<<"\n";
            if(now-arenaAt>=std::chrono::seconds(5)){ arenaAt=now; try { Arena(out,stamp); } catch(...) {} }
            try { SpawnStall::StuckPacks(out,stamp); } catch(...) {}
            if(!registry) return;
            int roundKeys=0, armed=0;
            for(int i=0;i<num && i<2048;i++){
                uint64_t key=0; uintptr_t rec=0;
                if(!Peek(data+i*0x18,key) || !key) continue;
                const auto& text=Key(key);
                if(text.empty()) continue;
                roundKeys++;
                auto* object=Peek(data+i*0x18+8,rec) && rec ? Weak(rec+0x48) : nullptr;
                if(!object) continue;
                armed++;
                out<<stamp<<"\tkey\t"<<std::string(text.begin(),text.end());
                const uintptr_t o=reinterpret_cast<uintptr_t>(object);
                uint64_t level=0;
                const bool ours=Peek(o+0xe0b0,level) && level && ArenaReady::IsOurs(level);
                out<<"\tterritory="<<Narrow(object->GetFullName())<<"\tddcc="<<Field<int32_t>(o+0xddcc)<<"\tddd0="<<Field<int32_t>(o+0xddd0)<<"\te0ac="<<Field<int32_t>(o+0xe0ac)
                   <<"\tours="<<ours<<"\tpartner="<<(Weak(o+0xe0b8)!=nullptr);
                int32_t count=0; uintptr_t spawns=0;
                Peek(o+0xd610,count);
                if(!Peek(o+0xd600,spawns) || !spawns) spawns=o+0xbf80;
                out<<"\tspawns="<<count<<":";
                for(int s=0;s<count && s<32;s++) out<<(s?",":"")<<Field<int32_t>(spawns+s*0xf0+0x10);
                out<<"\n";
            }
            out<<stamp<<"\tround_keys\t"<<roundKeys<<"\twith_territory\t"<<armed<<"\n";
        }
    }

    // Mako infusions from real accessories (owner design 2026-11-10). The Lua
    // writes junon-infusions.req in the mod's folder whenever the run's picks
    // or the battle phase change:
    //   run <token>        the run (echoed in the ack; Lua offers accessory
    //                      infusions only once this helper has answered "ready")
    //   phase battle|idle  idle: between rounds or outside a course
    //   acc E_ACC_0211     one line per accessory whose effects the party gets
    // No "acc" line (or an empty file) ends the run and removes everything.
    //
    // How (static analysis of ff7rebirth_.exe, image base 0x140000000,
    // 2026-11-10): every party member's data block (party data manager
    // *(*(0x1492a0440)+0x490), block mgr+0x88+((type*4+variant)*0x22e8)) holds
    // at +0x2040 a TMap<FName, TArray<TSharedPtr<SkillEntry>>> keyed WEAPON,
    // ARMOR, ACCESSORY, WEAPON_UPGRADE and PCREINFORCED. We add our own key
    // (JUNON_INFUSION) and fill it with the skill rows of real Equipment rows
    // through the game's own function (0x1415c9544), as equipping does for the
    // ACCESSORY key. Nothing is equipped and no item, equipment ID or save field
    // changes. The game's readers sum every key live, so most effects work at
    // once. Materia accessories (type 100) only reach the materia lists, and the
    // battle, through the parameter builder (0x140f3e2e4, "re-apply skills" and
    // "recompute status"), which runs only while idle (between rounds), so they
    // count from the next round. The accessories' ailment resistances are kept
    // at least at the row's values in the block's resist bytes (+0x20b0 x16,
    // +0x20c0 x3), which battle setup copies: also from the next round.
    // Clean-up (no accessories, a new world or a new party manager) clears our
    // key in every variant and lets the builder rebuild stats, materia lists and
    // resistances from the real equipment.
    //
    // Every game function's first bytes are compared with this build's before
    // first use; any difference (another game version) disables the feature,
    // with the reason in the ack and the log. Each call is SEH-guarded: a fault
    // disables the feature for the session.
    namespace InfusionSkills
    {
        constexpr uintptr_t ImageBase=0x140000000;
        constexpr uint8_t PartyTypes=7;          // EPlayerType 0..6, Cloud .. Cait Sith
        constexpr uint8_t Variants=4;
        constexpr uintptr_t BlockStart=0x88, BlockSize=0x22e8, SkillMap=0x2040, StatusResist=0x20b0, SpecialResist=0x20c0;
        constexpr size_t MaxAccessories=64;
        struct RawArray { void* data; int32_t num; int32_t max; };
        // The game's equipment accessor (vtable 0x1456ba768; the row at +8).
        struct Accessor { void* vtable; void* row; uint64_t extra; uint8_t flag; uint8_t pad[7]; };
        static_assert(sizeof(Accessor)==0x20);
        // UpdatePlayerParameter's request: about 0xd0 bytes, all zero but our flags.
        struct Request { alignas(16) uint8_t bytes[0x100]; };

        using MgrFn=void*(__fastcall*)();
        using BlockFn=uint8_t*(__fastcall*)(void* mgr,uint8_t playerType);
        using MapKeyFn=void(__fastcall*)(void* map,uint64_t key);
        using MapFindFn=RawArray*(__fastcall*)(void* map,uint64_t key);
        using AccessorFn=Accessor*(__fastcall*)(Accessor* out,uint64_t equipmentId);
        using AddRowFn=void(__fastcall*)(void* map,uint64_t key,Accessor* copy,uint8_t skipMateriaRecord);
        using ResistFn=uint8_t(__fastcall*)(Accessor* accessor,int32_t index);
        using UpdateFn=void(__fastcall*)(uint8_t* block,Request* request);
        using RequestDtorFn=void(__fastcall*)(Request* request);
        using QueryFn=bool(__fastcall*)(void* mgr,float* out,uint8_t playerType,uint8_t type);

        // Address in this build and its exact first bytes (rel32 and RIP
        // displacements included: they pin the callees and globals too).
        struct Site { const char* name; uintptr_t va; const char* bytes; };
        // Per game build (GameBuildId), in Sites order. Epic 1.005 found offline 2026-11-13 by instruction
        // matching and callers (Update: 4 callers agree, RequestDtor: 5); the party block layout (0x88 +
        // n*0x22e8, 0x2040/0x20b0/0x20c0) and the request fields Update reads are unchanged. Query (a
        // diagnostic read only) was not found on 1.005: optional there (va 0).
        constexpr Site SteamSites[]={
            {"Mgr",0x140a690c0,"48 8B 0D 79 73 83 08 33 C0 48 85 C9 74 07 48 8B 81 90 04 00 00 C3"},
            {"Block",0x140ac3c7c,"48 89 5C 24 08 57 B8 20 00 00 00 E8 D4 C4 69 01 48 2B E0 0F B6 DA 48 8B F9 80 FB 0F 73 2B E8 85"},
            {"MapAddKey",0x1413e6660,"48 89 54 24 10 53 B8 20 00 00 00 E8 F0 9A D7 00 48 2B E0 4C 8B C2 48 8B D9 48 8D 54 24 30 E8 61"},
            {"MapFind",0x1412eee58,"40 53 B8 20 00 00 00 E8 FC 12 E7 00 48 2B E0 4C 8B C2 48 8B D9 48 8D 54 24 30 E8 6D C9 68 FF 83"},
            {"MapClearKey",0x141870070,"48 85 D2 74 74 48 89 5C 24 08 48 89 74 24 18 57 B8 20 00 00 00 E8 D6 00 8F 00 48 2B E0 4C 8B C2"},
            {"MakeAccessor",0x140be30ac,"40 53 B8 20 00 00 00 E8 A8 D0 57 01 48 2B E0 33 C0 48 8B D9 48 89 41 08 88 41 18 48 89 44 24 30"},
            {"AddRow",0x1415c9544,"48 89 5C 24 08 44 88 4C 24 20 55 56 57 41 54 41 55 41 56 41 57 48 8D 6C 24 D9 B8 F0 00 00 00 E8 F8 6B B9 00 48 2B E0 C5 F8 29 B4 24 E0 00 00 00"},
            {"StatusResist",0x14140477c,"B8 28 00 00 00 E8 DA B9 D5 00 48 2B E0 48 63 C2 48 8D 15 2D E0 E1 04 48 83 C4 28 48 FF 24 C2 CC"},
            {"SpecialResist",0x1414047bc,"B8 28 00 00 00 E8 9A B9 D5 00 48 2B E0 48 63 C2 48 8D 15 CD DF E1 04 48 83 C4 28 48 FF 24 C2 CC"},
            {"Update",0x140f3e2e4,"48 89 5C 24 18 55 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 C0 FE FF FF B8 40 02 00 00 E8 5A 1E"},
            {"RequestDtor",0x140be7368,"48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 B8 20 00 00 00 E8 DE 8D 57 01 48 2B E0 33 ED 48"},
            {"Query",0x1410092a8,"44 88 4C 24 20 53 B8 80 00 00 00 E8 A8 6E 15 01 48 2B E0 83 22 00 48 8B DA 41 8A D0 E8 B3 A9 AB"},
        };
        constexpr Site EpicSites[]={
            {"Mgr",0x14092deec,"48 8B 0D 6D A6 8A 08 33 C0 48 85 C9 74 07 48 8B 81 90 04 00 00 C3"},
            {"Block",0x140f72e34,"48 89 5C 24 08 57 B8 20 00 00 00 E8 3C 8D 1F 01 48 2B E0 0F B6 DA 48 8B F9 80 FB 0F 73 2B E8 BD"},
            {"MapAddKey",0x141278f64,"48 89 54 24 10 53 B8 20 00 00 00 E8 0C 2C EF 00 48 2B E0 4C 8B C2 48 8B D9 48 8D 54 24 30 E8 A1"},
            {"MapFind",0x140c2c694,"40 53 B8 20 00 00 00 E8 E0 F4 53 01 48 2B E0 4C 8B C2 48 8B D9 48 8D 54 24 30 E8 75 5F CD FF 83"},
            {"MapClearKey",0x14181b654,"48 85 D2 74 77 48 89 5C 24 08 48 89 74 24 18 57 B8 20 00 00 00 E8 12 05 95 00 48 2B E0 4C 8B C2"},
            {"MakeAccessor",0x1407ff32c,"40 53 B8 20 00 00 00 E8 48 C8 96 01 48 2B E0 33 C0 48 8B D9 48 89 41 08 88 41 18 48 89 44 24 30"},
            {"AddRow",0x14095be04,"48 89 5C 24 08 44 88 4C 24 20 55 56 57 41 54 41 55 41 56 41 57 48 8D 6C 24 D9 B8 F0 00 00 00 E8 58 FD 80 01 48 2B E0 C5 F8 29 B4 24 E0 00 00 00"},
            {"StatusResist",0x1409618ac,"B8 28 00 00 00 E8 CA A2 80 01 48 2B E0 48 63 C2 48 8D 15 CD 86 80 05 48 8B 14 C2 48 83 C4 28 48"},
            {"SpecialResist",0x1409618f4,"B8 28 00 00 00 E8 82 A2 80 01 48 2B E0 48 63 C2 48 8D 15 0D 87 80 05 48 8B 14 C2 48 83 C4 28 48"},
            {"Update",0x140c2a79c,"48 89 5C 24 18 55 56 57 41 54 41 55 41 56 41 57 48 8D AC 24 A0 FE FF FF B8 60 02 00 00 E8 C2 13"},
            {"RequestDtor",0x140dab118,"48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 B8 20 00 00 00 E8 4E 0A 3C 01 48 2B E0 33 ED 48"},
            {"Query",0,""},
        };
        static_assert(std::size(SteamSites)==std::size(EpicSites));
        Site Mgr,Block,MapAddKey,MapFind,MapClearKey,MakeAccessor,AddRow,StatusGetter,SpecialGetter,Update,RequestDtor,Query;
        Site* const Sites[]={&Mgr,&Block,&MapAddKey,&MapFind,&MapClearKey,&MakeAccessor,&AddRow,&StatusGetter,&SpecialGetter,&Update,&RequestDtor,&Query};

        std::string RequestPath() { return Shared("junon-infusions.req"); }
        std::string AckPath() { return Shared("junon-infusions.ack"); }
        uintptr_t base=0;
        int state=0;                 // 0 unchecked, 1 ready, -1 disabled
        std::string disabled;        // why
        template<class F> F At(const Site& s){ return reinterpret_cast<F>(s.va-ImageBase+base); }
        void Log(const std::string& line)
        {
            const auto stamp=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            std::ofstream(Dev("junon-infusions.tsv"),std::ios::app)<<stamp<<"\t"<<line<<"\n";
        }

        // --- SEH-guarded game calls (plain data only inside __try) ---
        bool ByteAt(uintptr_t at,uint8_t& out){ __try { out=*reinterpret_cast<const uint8_t*>(at); return true; } __except(1) { return false; } }
        int Hex(char c){ return c>='0'&&c<='9'?c-'0':c>='A'&&c<='F'?c-'A'+10:c>='a'&&c<='f'?c-'a'+10:-1; }
        bool Matches(const Site& s)
        {
            uintptr_t at=s.va-ImageBase+base;
            for(const char* p=s.bytes;;){
                while(*p==' ') ++p;
                if(!*p) return true;
                const int hi=Hex(p[0]), lo=hi<0?-1:Hex(p[1]);
                uint8_t got=0;
                if(lo<0 || !ByteAt(at++,got) || got!=uint8_t(hi*16+lo)) return false;
                p+=2;
            }
        }
        bool CallMgr(void*& out){ __try { out=At<MgrFn>(Mgr)(); return true; } __except(1) { return false; } }
        bool CallBlock(void* mgr,uint8_t pt,uint8_t*& out){ __try { out=At<BlockFn>(Block)(mgr,pt); return true; } __except(1) { return false; } }
        bool CallFind(void* map,uint64_t key,RawArray*& out){ __try { out=At<MapFindFn>(MapFind)(map,key); return true; } __except(1) { return false; } }
        bool CallAddKey(void* map,uint64_t key){ __try { At<MapKeyFn>(MapAddKey)(map,key); return true; } __except(1) { return false; } }
        bool CallClearKey(void* map,uint64_t key){ __try { At<MapKeyFn>(MapClearKey)(map,key); return true; } __except(1) { return false; } }
        bool CallAccessor(Accessor* out,uint64_t id){ __try { At<AccessorFn>(MakeAccessor)(out,id); return true; } __except(1) { return false; } }
        bool CallAddRow(void* map,uint64_t key,Accessor* copy){ __try { At<AddRowFn>(AddRow)(map,key,copy,1); return true; } __except(1) { return false; } }
        bool CallResist(const Site& s,Accessor* acc,int32_t index,uint8_t& out){ __try { out=At<ResistFn>(s)(acc,index); return true; } __except(1) { return false; } }
        bool CallQuery(void* mgr,uint8_t pt,uint8_t type,float& out,bool& found){ if(!Query.va) return false; __try { out=0; found=At<QueryFn>(Query)(mgr,&out,pt,type); return true; } __except(1) { return false; } }
        // UpdatePlayerParameter with only "re-apply skills" (+0xbf: entries,
        // materia lists, resistances) and "recompute status" (+0xbd).
        bool CallRefresh(uint8_t* block)
        {
            __try {
                Request r{};
                r.bytes[0xbd]=1; r.bytes[0xbf]=1;
                *reinterpret_cast<uint8_t**>(r.bytes+0xc8)=block;
                At<UpdateFn>(Update)(block,&r);
                At<RequestDtorFn>(RequestDtor)(&r);
                return true;
            } __except(1) { return false; }
        }
        bool ReadEntries(RawArray* arr,uint8_t* types,int32_t max,int32_t& count)
        {
            __try {
                count=0;
                for(int32_t i=0;arr && i<arr->num && count<max;i++){
                    const uint8_t* entry=*reinterpret_cast<uint8_t* const*>(reinterpret_cast<uint8_t*>(arr->data)+i*16);
                    if(entry) types[count++]=entry[8];   // EEndSkillEffectType
                }
                return true;
            } __except(1) { return false; }
        }
        bool RaiseResist(uint8_t* block,const uint8_t* status,const uint8_t* special)
        {
            __try {
                for(int i=0;i<16;i++) if(block[StatusResist+i]<status[i]) block[StatusResist+i]=status[i];
                for(int i=0;i<3;i++) if(block[SpecialResist+i]<special[i]) block[SpecialResist+i]=special[i];
                return true;
            } __except(1) { return false; }
        }

        struct Wanted { std::string id; uint64_t name=0; uint8_t status[16]{}; uint8_t special[3]{}; };
        struct Slot {                    // one party block (type, variant)
            std::vector<uint64_t> applied; // the accessories it holds, in request order
            int32_t entries=0;
            bool waiting=false;          // a change that must wait for idle
            bool touched=false;          // we changed it: rebuild it on clean-up
            bool pending=false;          // waits for the builder (at the next idle)
            std::string types;
        };
        std::vector<Wanted> wanted;
        std::vector<std::string> notes;  // per-accessory ack lines
        uint8_t wantStatus[16]{}, wantSpecial[3]{};
        uint64_t key=0;                  // FName JUNON_INFUSION
        std::string run="none", phase="idle";
        uint32_t generation=0;
        Slot slots[PartyTypes][Variants];
        void* manager=nullptr;
        std::filesystem::file_time_type stamp{}, started{};
        auto last=std::chrono::steady_clock::time_point{};
        auto holdUntil=std::chrono::steady_clock::time_point{};   // no builder until then (after a world change)
        // A new world: a GameModeBase receives BeginPlay.
        uint32_t beginPlay=0;
        RC::Unreal::UClass* gameMode=nullptr;
        RC::Unreal::UObject* lastGameMode=nullptr;
        bool worldChanged=false;
        bool dirty=false;                // the ack needs rewriting

        void Disable(const std::string& why)
        {
            state=-1; disabled=why;
            Log("disabled\t"+why);
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<"infusions_disabled "<<why<<"\n";
            dirty=true;
        }
        uint64_t Raw(const RC::Unreal::FName& n){ uint64_t raw=0; std::memcpy(&raw,&n,sizeof(raw)); return raw; }
        // The FName of a name the game already has, or 0 (compared back as text).
        uint64_t Existing(const std::string& text)
        {
            const std::wstring wide(text.begin(),text.end());
            RC::Unreal::FName n(wide.c_str(),RC::Unreal::FNAME_Find);
            const uint64_t raw=Raw(n);
            if(!uint32_t(raw)) return 0;
            const auto back=n.ToString();
            return back.size()==wide.size() && _wcsicmp(back.c_str(),wide.c_str())==0 ? raw : 0;
        }
        bool Init()
        {
            if(state) return state==1;
            base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
            started=std::filesystem::file_time_type::clock::now();
            const int build=GameBuild();
            if(build<0){ Disable("unknown_game_build"); return false; }
            const Site* table=build==Epic1005?EpicSites:SteamSites;
            for(size_t i=0;i<std::size(Sites);i++) *Sites[i]=table[i];
            for(const Site* s:Sites)
                if(s->va && !Matches(*s)){
                    std::ostringstream o; o<<"signature_mismatch "<<s->name<<" 0x"<<std::hex<<s->va;
                    Disable(o.str());
                    return false;
                }
            RC::Unreal::FName k(STR("JUNON_INFUSION"),RC::Unreal::FNAME_Add);
            key=Raw(k);
            if(!uint32_t(key) || k.ToString()!=STR("JUNON_INFUSION")){ Disable("key_name_failed"); return false; }
            RC::Unreal::FName bp(STR("ReceiveBeginPlay"),RC::Unreal::FNAME_Find);
            beginPlay=bp.GetComparisonIndex();
            gameMode=RC::Unreal::UObjectGlobals::StaticFindObject<RC::Unreal::UClass*>(nullptr,nullptr,STR("/Script/Engine.GameModeBase"));
            state=1;
            Log(std::string("ready\tworld_watch=")+(beginPlay && gameMode?"1":"0"));
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)<<"infusions_enabled\n";
            dirty=true;
            return true;
        }
        uint8_t* BlockAt(void* mgr,uint8_t pt,uint8_t variant)
        {
            return reinterpret_cast<uint8_t*>(mgr)+BlockStart+(uintptr_t(pt)*Variants+variant)*BlockSize;
        }
        void ReadRequest()
        {
            std::vector<Wanted> next;
            std::vector<std::string> nextNotes;
            std::string nextRun="none", nextPhase="idle";
            uint8_t status[16]{}, special[3]{};
            std::error_code ec;
            const auto t=std::filesystem::last_write_time(RequestPath(),ec);
            const bool stale=!ec && t<started;   // left over from an earlier game session
            std::ifstream in(RequestPath());
            std::string line;
            while(!stale && std::getline(in,line)){
                std::istringstream words(line);
                std::string kind, value;
                if(!(words>>kind>>value)) continue;
                if(kind=="run") nextRun=value;
                else if(kind=="phase") nextPhase=value=="battle"?"battle":"idle";
                else if(kind=="acc"){
                    auto refuse=[&](const char* why){ nextNotes.push_back("acc "+value+" refused "+why); Log("refused\t"+value+"\t"+why); };
                    const bool shape=value.size()==10 && value.rfind("E_ACC_",0)==0 &&
                                     std::all_of(value.begin()+6,value.end(),[](char c){ return c>='0' && c<='9'; });
                    if(!shape){ refuse("not_an_accessory_id"); continue; }
                    if(next.size()>=MaxAccessories){ refuse("too_many"); continue; }
                    if(std::any_of(next.begin(),next.end(),[&](const Wanted& w){ return w.id==value; })){ refuse("duplicate"); continue; }
                    Wanted w; w.id=value; w.name=Existing(value);
                    if(!w.name){ refuse("unknown_name"); continue; }
                    Accessor acc{};
                    if(!CallAccessor(&acc,w.name)){ Disable("fault_in_MakeAccessor"); return; }
                    if(!acc.row){ refuse("not_in_equipment_table"); continue; }
                    std::string resist;
                    for(int i=0;i<16;i++){
                        if(!CallResist(StatusGetter,&acc,i,w.status[i])){ Disable("fault_in_StatusResist"); return; }
                        if(w.status[i]>100) w.status[i]=100;
                        if(w.status[i]){ status[i]=(std::max)(status[i],w.status[i]); resist+=" status"+std::to_string(i)+"="+std::to_string(w.status[i]); }
                    }
                    for(int i=0;i<3;i++){
                        if(!CallResist(SpecialGetter,&acc,i,w.special[i])){ Disable("fault_in_SpecialResist"); return; }
                        if(w.special[i]>100) w.special[i]=100;
                        if(w.special[i]){ special[i]=(std::max)(special[i],w.special[i]); resist+=" special"+std::to_string(i)+"="+std::to_string(w.special[i]); }
                    }
                    nextNotes.push_back("acc "+value+" ok"+(resist.empty()?"":" resist"+resist));
                    next.push_back(w);
                }
            }
            if(stale) Log("stale_request_ignored");
            bool same=next.size()==wanted.size();
            for(size_t i=0;same && i<next.size();i++) same=next[i].name==wanted[i].name;
            if(!same) generation++;
            wanted=std::move(next); notes=std::move(nextNotes);
            std::memcpy(wantStatus,status,sizeof status); std::memcpy(wantSpecial,special,sizeof special);
            run=nextRun; phase=nextPhase;
            Log("request\trun="+run+"\tphase="+phase+"\taccessories="+std::to_string(wanted.size())+"\tgeneration="+std::to_string(generation));
            dirty=true;
        }
        // Clear our key in every block and queue the builder for the blocks we changed.
        bool ClearAll(void* mgr,const char* why)
        {
            int cleared=0;
            for(uint8_t pt=0;pt<PartyTypes;pt++) for(uint8_t v=0;v<Variants;v++){
                Slot& s=slots[pt][v];
                uint8_t* block=BlockAt(mgr,pt,v);
                RawArray* arr=nullptr;
                if(!CallFind(block+SkillMap,key,arr)){ Disable("fault_in_MapFind"); return false; }
                if(arr && arr->num>0){
                    if(!CallClearKey(block+SkillMap,key)){ Disable("fault_in_MapClearKey"); return false; }
                    cleared++;
                }
                if(s.touched) s.pending=true;
                s.applied.clear(); s.entries=0; s.waiting=false; s.types.clear();
            }
            if(cleared) Log(std::string("cleared\t")+why+"\tblocks="+std::to_string(cleared));
            notes.push_back(std::string("cleared ")+why+" blocks="+std::to_string(cleared));
            dirty=true;
            return true;
        }
        // Bring one block up to the request. New picks are appended, never
        // re-created: in battle, entries the game may still hold are never freed.
        // Any other change (a different set) waits for idle, then the key is
        // cleared and refilled.
        bool Fill(void* mgr,uint8_t pt,uint8_t v,uint8_t* block,bool idle)
        {
            Slot& s=slots[pt][v];
            void* map=block+SkillMap;
            RawArray* arr=nullptr;
            if(!CallFind(map,key,arr)){ Disable("fault_in_MapFind"); return false; }
            if(!arr){
                if(!CallAddKey(map,key)){ Disable("fault_in_MapAddKey"); return false; }
                if(!CallFind(map,key,arr)){ Disable("fault_in_MapFind"); return false; }
                if(!arr){ Disable("key_add_failed"); return false; }
            }
            bool prefix=s.applied.size()<=wanted.size() && arr->num==s.entries;
            for(size_t i=0;prefix && i<s.applied.size();i++) prefix=s.applied[i]==wanted[i].name;
            if(prefix && s.applied.size()==wanted.size()) return true;
            if(!prefix){
                if(!idle){
                    if(!s.waiting){ s.waiting=true; Log("rebuild_waits_for_idle	pt="+std::to_string(pt)); }
                    return true;
                }
                if(!CallClearKey(map,key)){ Disable("fault_in_MapClearKey"); return false; }
                s.applied.clear();
            }
            s.waiting=false;
            for(size_t i=s.applied.size();i<wanted.size();i++){
                Accessor acc{};
                if(!CallAccessor(&acc,wanted[i].name)){ Disable("fault_in_MakeAccessor"); return false; }
                if(acc.row){
                    Accessor copy=acc;             // the callee destroys its copy
                    if(!CallAddRow(map,key,&copy)){ Disable("fault_in_AddRow"); return false; }
                }
                s.applied.push_back(wanted[i].name);
            }
            if(!CallFind(map,key,arr) || !arr){ Disable("key_lost_after_fill"); return false; }
            uint8_t types[64]{}; int32_t count=0;
            if(!ReadEntries(arr,types,64,count)){ Disable("fault_reading_entries"); return false; }
            s.entries=arr->num; s.touched=true;
            s.types.clear();
            bool builder=false;
            for(int32_t i=0;i<count;i++){
                s.types+=(i?",":"")+std::to_string(types[i]);
                // Stats (1..10), materia (100) and slots (115) go through the builder.
                if((types[i]>=1 && types[i]<=10) || types[i]==100 || types[i]==115) builder=true;
            }
            // Touched blocks are rebuilt at clean-up even without builder types.
            s.pending=s.pending || builder;
            std::ostringstream o;
            o<<"applied	pt="<<int(pt)<<"	variant="<<int(v)<<"	accessories="<<s.applied.size()<<"	entries="<<s.entries
             <<"	types="<<s.types<<"	builder="<<builder<<"	phase="<<phase;
            // Ask the game's own reader for each type (in battle only, where the
            // game itself asks; conditional entries may look at battle state).
            std::vector<uint8_t> asked;
            for(int32_t i=0;phase=="battle" && i<count;i++){
                if(std::find(asked.begin(),asked.end(),types[i])!=asked.end()) continue;
                asked.push_back(types[i]);
                float sum=0; bool found=false;
                if(CallQuery(mgr,pt,types[i],sum,found)){ int32_t bits=0; std::memcpy(&bits,&sum,4); o<<"	q"<<int(types[i])<<"="<<found<<":"<<sum<<"/"<<bits; }
            }
            Log(o.str());
            dirty=true;
            return true;
        }
        void WriteAck()
        {
            std::ostringstream o;
            o<<"run "<<run<<"\n";
            o<<"status "<<(state==1?"ready":"disabled "+disabled)<<"\n";
            o<<"phase "<<phase<<"\n";
            for(const auto& n:notes) o<<n<<"\n";
            for(uint8_t pt=0;pt<PartyTypes;pt++) for(uint8_t v=0;v<Variants;v++){
                const Slot& s=slots[pt][v];
                if(s.applied.empty() && !s.pending) continue;
                o<<"party "<<int(pt)<<" variant "<<int(v)<<" entries "<<s.entries<<" types "<<(s.types.empty()?"-":s.types)
                 <<" builder "<<(s.pending?"pending":"done")<<(s.waiting?" waiting_for_idle":"")<<"\n";
            }
            const std::string path=AckPath(), tmp=path+".tmp";
            { std::ofstream out(tmp,std::ios::trunc); out<<o.str(); }
            dirty=!MoveFileExA(tmp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING);   // retried while the Lua reads it
        }
        // Every ProcessEvent call (hot path): one name compare.
        void Event(RC::Unreal::UObject* object,RC::Unreal::UFunction* function)
        {
            if(state!=1 || !beginPlay || !gameMode || !function || !object) return;
            // UObjectBase::NamePrivate at +0x18 (as ColosseumScan reads it): its comparison index.
            if(*reinterpret_cast<const uint32_t*>(reinterpret_cast<uintptr_t>(function)+0x18)!=beginPlay) return;
            for(auto* c=object->GetClassPrivate();c;c=c->GetSuperClass())
                if(c==gameMode){
                    if(object!=lastGameMode){ lastGameMode=object; worldChanged=true; }
                    return;
                }
        }
        // Game thread, at a safe point, every 250 ms (FrameWork).
        void Tick()
        {
            const auto now=std::chrono::steady_clock::now();
            if(state==0) Init();
            std::error_code ec;
            const auto t=std::filesystem::last_write_time(RequestPath(),ec);
            const bool fresh=!ec && t!=stamp;
            if(fresh){ stamp=t; if(state==1) ReadRequest(); else { run="none"; dirty=true; } }
            if(fresh && state!=1){
                // Echo the run even when disabled, so the Lua knows not to offer.
                std::ifstream in(RequestPath()); std::string kind, value;
                while(in>>kind){ if(kind=="run" && in>>value) run=value; }
            }
            if(state==1){
                void* mgr=nullptr;
                if(!CallMgr(mgr)) Disable("fault_in_Mgr");
                else if(mgr){
                    if(manager && mgr!=manager){
                        // A new party manager: our earlier blocks are gone.
                        for(auto& row:slots) for(auto& s:row) s=Slot{};
                        wanted.clear(); generation++; phase="idle";
                        notes.push_back("party_manager_changed");
                        Log("party_manager_changed"); dirty=true;
                    }
                    manager=mgr;
                    if(worldChanged){
                        // A new world ends any run: drop the request until the Lua writes a new one.
                        worldChanged=false;
                        if(!wanted.empty()) generation++;
                        wanted.clear(); phase="idle";
                        std::memset(wantStatus,0,sizeof wantStatus); std::memset(wantSpecial,0,sizeof wantSpecial);
                        Log("world_change");
                        holdUntil=now+std::chrono::seconds(3);   // let the new world settle first
                        ClearAll(mgr,"world_change");
                    }else if(fresh && wanted.empty()){
                        ClearAll(mgr,"request_empty");
                    }
                    if(state==1 && !wanted.empty())
                        for(uint8_t pt=0;pt<PartyTypes && state==1;pt++){
                            uint8_t* block=nullptr;
                            if(!CallBlock(mgr,pt,block)){ Disable("fault_in_Block"); break; }
                            if(!block) continue;
                            const uintptr_t offset=uintptr_t(block-BlockAt(mgr,pt,0));
                            if(offset%BlockSize || offset/BlockSize>=Variants) continue;
                            Fill(mgr,pt,uint8_t(offset/BlockSize),block,phase=="idle");
                        }
                    // The builder only between rounds (idle): it recomputes stats and lists.
                    if(state==1 && phase=="idle" && now>=holdUntil)
                        for(uint8_t pt=0;pt<PartyTypes && state==1;pt++) for(uint8_t v=0;v<Variants;v++){
                            Slot& s=slots[pt][v];
                            if(!s.pending) continue;
                            if(!CallRefresh(BlockAt(mgr,pt,v))){ Disable("fault_in_Update"); break; }
                            s.pending=false;
                            if(s.applied.empty()) s.touched=false;   // rebuilt from real equipment only
                            Log("builder\tpt="+std::to_string(pt)+"\tvariant="+std::to_string(v));
                            dirty=true;
                        }
                    // Resistances: at least the accessories' values, after any rebuild.
                    if(state==1 && !wanted.empty())
                        for(uint8_t pt=0;pt<PartyTypes;pt++){
                            uint8_t* block=nullptr;
                            if(!CallBlock(mgr,pt,block) || !block) continue;
                            if(!RaiseResist(block,wantStatus,wantSpecial)){ Disable("fault_in_resist_write"); break; }
                            const uintptr_t offset=uintptr_t(block-BlockAt(mgr,pt,0));
                            if(!(offset%BlockSize) && offset/BlockSize<Variants){
                                bool any=false;
                                for(uint8_t x:wantStatus) any=any||x;
                                for(uint8_t x:wantSpecial) any=any||x;
                                if(any) slots[pt][offset/BlockSize].touched=true;
                            }
                        }
                }
            }
            if(dirty) WriteAck();
        }
    }

    // Opt-in (junon-watch.on): find the code that assigns a spawn location. When our
    // arena territory's first spawn entry is waiting (state 2) at the placeholder
    // location (-400000,-200000,0) at +0x90, arm hardware watchpoint DR0 on that
    // field in every thread; a vectored handler records the writing instruction and
    // the return addresses on its stack (junon-watch.tsv), then disarms itself.
    namespace Watch
    {
        constexpr uintptr_t ImageBase=0x140000000, FieldGlobal=0x149001588;
        constexpr uint64_t Placeholder=0xc8435000c8c35000ull;
        struct Hit { uintptr_t rip; uintptr_t stack[24]; };
        Hit hits[8]{};
        volatile LONG count=0;
        uintptr_t lo=0,hi=0;
        LONG CALLBACK Handler(PEXCEPTION_POINTERS e)
        {
            if(e->ExceptionRecord->ExceptionCode!=EXCEPTION_SINGLE_STEP) return EXCEPTION_CONTINUE_SEARCH;
            CONTEXT* c=e->ContextRecord;
            if(!(c->Dr6&1)) return EXCEPTION_CONTINUE_SEARCH;
            const LONG i=InterlockedIncrement(&count)-1;
            if(i<8){
                hits[i].rip=c->Rip;
                const uintptr_t* sp=reinterpret_cast<const uintptr_t*>(c->Rsp);
                int n=0;
                for(int k=0;k<160 && n<24;k++){
                    uintptr_t v=0;
                    __try { v=sp[k]; } __except(1) { break; }
                    if(v>=lo && v<hi) hits[i].stack[n++]=v;
                }
            }
            c->Dr6=0;
            if(i>=7) c->Dr7&=~0x000F0003ull; // keep the first eight writes, then off
            return EXCEPTION_CONTINUE_EXECUTION;
        }
        template<class T> bool Peek(uintptr_t at,T& out)
        {
            if(at<0x10000) return false;
            __try { out=*reinterpret_cast<const T*>(at); return true; } __except(1) { return false; }
        }
        void SetAll(uintptr_t addr,bool on)
        {
            HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
            if(snap==INVALID_HANDLE_VALUE) return;
            THREADENTRY32 te{}; te.dwSize=sizeof(te);
            const DWORD pid=GetCurrentProcessId(), self=GetCurrentThreadId();
            for(BOOL ok=Thread32First(snap,&te);ok;ok=Thread32Next(snap,&te)){
                if(te.th32OwnerProcessID!=pid || te.th32ThreadID==self) continue;
                HANDLE t=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,te.th32ThreadID);
                if(!t) continue;
                if(SuspendThread(t)!=DWORD(-1)){
                    CONTEXT ctx{}; ctx.ContextFlags=CONTEXT_DEBUG_REGISTERS;
                    if(GetThreadContext(t,&ctx)){
                        ctx.Dr7&=~0x000F0003ull;
                        if(on){ ctx.Dr0=addr; ctx.Dr7|=1ull|(1ull<<16)|(3ull<<18); } // L0, write, 4 bytes
                        SetThreadContext(t,&ctx);
                    }
                    ResumeThread(t);
                }
                CloseHandle(t);
            }
            CloseHandle(snap);
        }
        // Our territory's first spawn entry, or 0.
        uintptr_t FirstEntry(uintptr_t base)
        {
            uintptr_t g=0,r=0,data=0; int num=0;
            if(!Peek(FieldGlobal-ImageBase+base,g) || !Peek(g+0x278,r) || !Peek(r+0x7b8,data) || !Peek(r+0x7c0,num)) return 0;
            for(int i=0;i<num && i<2048;i++){
                uintptr_t rec=0; if(!Peek(data+i*0x18+8,rec) || !rec) continue;
                int32_t index=0; if(!Peek(rec+0x48,index) || index<=0) continue;
                auto* object=reinterpret_cast<const RC::Unreal::FWeakObjectPtr*>(rec+0x48)->Get();
                if(!object) continue;
                const uintptr_t o=reinterpret_cast<uintptr_t>(object);
                uintptr_t names=0; uint64_t first=0; int count=0;
                if(!Peek(o+0x178,names) || !Peek(o+0x180,count) || count<1 || !Peek(names,first)) continue;
                static uint64_t ourName=0;
                if(!ourName){
                    std::string n; for(auto ch:RC::Unreal::FName(int64_t(first)).ToString()) n.push_back(ch<128?char(ch):'?');
                    if(n!="UCBattle_TerritoryCmnActor") continue;
                    ourName=first;
                }
                if(first!=ourName) continue;
                return o; // the territory actor
            }
            return 0;
        }
        void Start()
        {
            if(GameBuild()!=SteamJan2025) return;   // dev diagnostics: old-build addresses only (not ported to 1.005)
            std::thread([]{
                const uintptr_t base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
                lo=base; hi=base+0x7000000;
                bool installed=false, armed=false, reported=false; uintptr_t target=0;
                auto armedAt=std::chrono::steady_clock::now();
                for(;;){
                    std::this_thread::sleep_for(std::chrono::milliseconds(armed?200:50));
                    if(!DevFlag("junon-watch.on")){
                        if(armed){ SetAll(0,false); armed=false; }
                        continue;
                    }
                    if(!installed){ AddVectoredExceptionHandler(1,Handler); installed=true; }
                    if(!armed && !reported){
                        // Arm on the territory's spawn-entry count (+0xd610) while it is idle
                        // between rounds: the first write is the code that builds a round's
                        // spawn entries (and, for spawns that work, their locations).
                        const uintptr_t o=FirstEntry(base);
                        uint8_t st=0xff;
                        if(o && Peek(o+0xddcc,st) && (st==0 || st==4)){
                            target=o+0xd610; SetAll(target,true); armed=true; armedAt=std::chrono::steady_clock::now();
                        }
                    }
                    if(armed && (count>=8 || (count>0 && std::chrono::steady_clock::now()-armedAt>std::chrono::seconds(90)) || std::chrono::steady_clock::now()-armedAt>std::chrono::seconds(600))){
                        SetAll(0,false); armed=false; reported=true;
                        std::ofstream out(Dev("junon-watch.tsv"),std::ios::app);
                        out<<"watch\ttarget\t"<<std::hex<<target<<"\tbase\t"<<base<<std::dec<<"\thits\t"<<count<<"\n";
                        for(LONG i=0;i<count && i<8;i++){
                            out<<"hit\t"<<i<<"\trip\t"<<std::hex<<(hits[i].rip-base+ImageBase);
                            for(auto v:hits[i].stack) if(v) out<<"\t"<<(v-base+ImageBase);
                            out<<std::dec<<"\n";
                        }
                    }
                }
            }).detach();
        }
    }

    // Opt-in (junon-trace.on): execution breakpoints (debug registers, no code
    // patching) on the round builder's helpers. Each call made for our arena
    // territory records its arguments and the block its third argument points
    // to (junon-trace.tsv): what the builder decides per enemy.
    namespace Trace
    {
        constexpr uintptr_t ImageBase=0x140000000;
        // DR0..DR3: spawn-point list for a size class; add one spawn entry;
        // list by size when mob distribution points exist; fly-check list.
        constexpr uintptr_t Targets[4]={0x141472b9c,0x141474044,0x1414729b8,0x141472c94};
        struct Call { int dr; uintptr_t rcx,rdx,r8,r9; uintptr_t stack[6]; uint8_t block[0xa0]; };
        Call calls[96]{};
        volatile LONG count=0;
        volatile uintptr_t territory=0; // our territory actor; 0 = record nothing
        LONG CALLBACK Handler(PEXCEPTION_POINTERS e)
        {
            if(e->ExceptionRecord->ExceptionCode!=EXCEPTION_SINGLE_STEP) return EXCEPTION_CONTINUE_SEARCH;
            CONTEXT* c=e->ContextRecord;
            const DWORD64 which=c->Dr6&0xf;
            if(!which) return EXCEPTION_CONTINUE_SEARCH;
            int dr=0; while(dr<4 && !(which&(1ull<<dr))) dr++;
            c->Dr6=0;
            c->EFlags|=0x10000; // resume flag: run the instruction, keep the breakpoint
            const uintptr_t t=territory;
            if(t && c->Rcx==t){
                const LONG i=InterlockedIncrement(&count)-1;
                if(i<96){
                    Call& k=calls[i];
                    k.dr=dr; k.rcx=c->Rcx; k.rdx=c->Rdx; k.r8=c->R8; k.r9=c->R9;
                    const uintptr_t* sp=reinterpret_cast<const uintptr_t*>(c->Rsp);
                    for(int s=0;s<6;s++){ __try { k.stack[s]=sp[5+s]; } __except(1) { k.stack[s]=0; } }
                    for(int b=0;b<0xa0;b++){ __try { k.block[b]=reinterpret_cast<const uint8_t*>(c->R8)[b]; } __except(1) { k.block[b]=0; } }
                }
            }
            return EXCEPTION_CONTINUE_EXECUTION;
        }
        void SetAll(uintptr_t base,bool on)
        {
            HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
            if(snap==INVALID_HANDLE_VALUE) return;
            THREADENTRY32 te{}; te.dwSize=sizeof(te);
            const DWORD pid=GetCurrentProcessId(), self=GetCurrentThreadId();
            for(BOOL ok=Thread32First(snap,&te);ok;ok=Thread32Next(snap,&te)){
                if(te.th32OwnerProcessID!=pid || te.th32ThreadID==self) continue;
                HANDLE h=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,te.th32ThreadID);
                if(!h) continue;
                if(SuspendThread(h)!=DWORD(-1)){
                    CONTEXT ctx{}; ctx.ContextFlags=CONTEXT_DEBUG_REGISTERS;
                    if(GetThreadContext(h,&ctx)){
                        ctx.Dr7&=~0xFFFF00FFull;
                        if(on){
                            ctx.Dr0=Targets[0]-ImageBase+base; ctx.Dr1=Targets[1]-ImageBase+base;
                            ctx.Dr2=Targets[2]-ImageBase+base; ctx.Dr3=Targets[3]-ImageBase+base;
                            ctx.Dr7|=0x55ull; // L0..L3, execute, length 1 (RW/LEN bits zero)
                        }
                        SetThreadContext(h,&ctx);
                    }
                    ResumeThread(h);
                }
                CloseHandle(h);
            }
            CloseHandle(snap);
        }
        void Start()
        {
            if(GameBuild()!=SteamJan2025) return;   // dev diagnostics: old-build addresses only (not ported to 1.005)
            std::thread([]{
                const uintptr_t base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
                bool installed=false, armed=false; LONG written=0;
                auto lastArm=std::chrono::steady_clock::now();
                for(;;){
                    std::this_thread::sleep_for(std::chrono::milliseconds(250));
                    const bool want=DevFlag("junon-trace.on");
                    if(!want){ if(armed){ SetAll(base,false); armed=false; } territory=0; continue; }
                    if(!installed){ AddVectoredExceptionHandler(1,Handler); installed=true; }
                    if(!territory){ territory=Watch::FirstEntry(base); }
                    // Re-arm now and then so threads created since get the breakpoints too.
                    if(territory && (!armed || std::chrono::steady_clock::now()-lastArm>std::chrono::seconds(5))){
                        SetAll(base,true); armed=true; lastArm=std::chrono::steady_clock::now();
                    }
                    const LONG n=count<96?count:96;
                    if(n>written){
                        std::ofstream out(Dev("junon-trace.tsv"),std::ios::app);
                        for(LONG i=written;i<n;i++){
                            const Call& k=calls[i];
                            out<<"call\t"<<i<<"\tfn\t"<<std::hex<<Targets[k.dr]<<"\trdx\t"<<k.rdx<<"\tr8\t"<<k.r8<<"\tr9\t"<<k.r9<<"\tstack";
                            for(auto v:k.stack) out<<"\t"<<v;
                            out<<"\tblock";
                            for(int b=0;b<0xa0;b+=8){ uint64_t q=0; std::memcpy(&q,k.block+b,8); out<<"\t"<<q; }
                            out<<std::dec<<"\n";
                        }
                        written=n;
                    }
                }
            }).detach();
        }
    }

    // ---- Spawn stall (development installs only) ----
    // Hang 3 (2026-11-10, full dump): a round's battle began but its enemies
    // never came. The sequence (+0x29c == 2) waited for the round's spawn
    // entries (state 2); their pop-server records (+0x1ac == 0) were never
    // activated because each spawn's CharaSpec pack entry stayed at state 2:
    // the game's load request for it waited on engine requests that the
    // engine's async loader no longer held (loader idle, ids pending for good).
    // While the Lua keeps junon-spawnstall.on (in battle, no enemy 20 s after
    // the battle began), log that chain once a second to junon-spawnstall.tsv:
    //  - the sequence's +0x298/+0x29c (ColosseumScan::Sequence);
    //  - the engine loader's queued and in-flight counters (Loader);
    //  - per spawn entry of our armed territory (+0xd600 or inline +0xbf80,
    //    count +0xd610, 0xf0 each: name +0, state +0x10): its pop-server record
    //    (pop=*(*(0x149001588)+0x180); map *(pop+0x10)+8, count +0x10, 0x18-byte
    //    {name, record}; record +0x1ac state, +0x44 priority, +0x118 flags) and
    //    its pack entries (pack loader l3=*(pop+0x18); map l3+0xf0, count
    //    +0xf8, 0x18-byte {name, value}; value {entries, count}; entry +0 type
    //    (1 CharaSpec), +4 name, +0x38 l3, +0x44 handle, +0x48 state: 2 issued
    //    by 0x140fb445c, 3 loaded once the poller 0x140e8d524 sees the handle
    //    done);
    //  - for an entry at state 2, whether its handle is still pending, and the
    //    game's request for it (list *(0x1490e6260)+8, count +0x10; request +8
    //    handle, +0x10 pack name, +0x38/+0x40 engine ids) with each id's
    //    pending state. "Pending" is the game's own check 0x140d77ea4 (a set
    //    under the game's lock), the only call made.
    // Reads are SEH-guarded; code is checked byte for byte first (Verify).
    //
    // Recovery (experimental; only while junon-spawnfix.on exists too). For a
    // CharaSpec pack entry that has waited at state 2 on the same handle for
    // FixAfter, once per entry, and only while the round waits for its spawns
    // (+0x29c == 2), the handle and every engine id of its request are still
    // pending and the engine loader holds nothing (queued and in-flight
    // counters 0: the load is lost, not slow): load each object listed for that
    // pack in junon-spawnfix-paths.tsv (telemetry folder; lines
    // "<pack name>\t<object path>", e.g. "CharaSpec_EN2246_01_Valron_RareEnd2\t
    // /Game/.../X.X_C") with LoadAsset_Blocking here at the safe point, keep
    // each rooted for RootFor, and only if every one returned an object that
    // StaticFindObject then finds, and the entry still holds the same handle at
    // state 2, write what the poller writes (+0x44 = -1, +0x48 = 3). The
    // scheduler 0x1408dc5a4 then activates the records on its next pass. Every
    // step is logged; any failed check writes nothing.
    // Not done, because not verified: turning a pack's item names (CharaPopPack
    // rows such as BluePrint_Character_Enemy_EN2246_01_Valron_RareEnd2) into
    // object paths (the game does it in 0x1410c2328/0x140c4bfe8, not decoded),
    // so the paths file is filled by hand; removing the dead request from the
    // game's list (it keeps polling its lost ids, harmless) and releasing its
    // handle (0x1416eec90).
    namespace SpawnStall
    {
        using ArenaReady::Peek;
        constexpr uintptr_t FieldGlobal=0x149001588, RequestList=0x1490e6260, IsLoadingFn=0x140d77ea4, PackPoll=0x140e8d524, PackIssueWrite=0x140fb44f7;
        constexpr ULONGLONG FixAfter=20000, RootFor=60000;   // ms
        int state=0;   // 0 unchecked, 1 verified, -1 unverified
        bool Verify()
        {
            if(state) return state==1;
            const bool ok=
                // IsLoading(handle): lea rcx,[lock]; call [EnterCriticalSection]; ...
                Code::Matches(IsLoadingFn,"48 89 5C 24 08 57 B8 20 00 00 00 E8 AC 82 3E 01 48 2B E0 48 63 F9 48 8D 0D 3F 6E A6 07 FF 15 F9 A8 8A 04") &&
                // The poller: mov ecx,[rbx+44]; call IsLoading; ... or dword [rbx+44],-1; mov dword [rbx+48],3
                Code::Matches(PackPoll,"40 53 B8 20 00 00 00 E8 30 2C 2D 01 48 2B E0 48 8B D9 8B 49 44 E8 66 A9 EE FF 84 C0 74 06 48 83 C4 20 5B C3 83 4B 44 FF C7 43 48 03 00 00 00") &&
                // The issuer: mov [rbx+44],eax (the handle); mov dword [rbx+48],2
                Code::Matches(PackIssueWrite,"B9 44 00 00 00 48 8B D3 89 04 0B C7 43 48 02 00 00 00");
            state=ok?1:-1;
            Event("spawn_stall_",ok?"checks_verified":"checks_unverified_unknown_build");
            return ok;
        }
        bool CallPending(int32_t id,bool& out)
        {
            __try { out=reinterpret_cast<bool(__fastcall*)(int32_t)>(Code::At(IsLoadingFn))(id); return true; }
            __except(1) { return false; }
        }
        // "1" pending, "0" done, "?" not checked, "fault".
        std::string Pending(int32_t id)
        {
            if(state!=1 || id<0) return "?";
            bool pending=false;
            return CallPending(id,pending) ? (pending?"1":"0") : "fault";
        }
        std::string Text(uint64_t raw){ return Stall::Narrow(RoundShuffle::Text(raw)); }
        // A TMap element array of 0x18-byte {FName key, value pointer}: the value for key, or 0.
        uintptr_t Lookup(uintptr_t data,int32_t num,uint64_t key)
        {
            for(int32_t i=0;i<num && i<8192;i++){
                uint64_t k=0; uintptr_t v=0;
                if(Peek(data+i*0x18,k) && k==key && Peek(data+i*0x18+8,v)) return v;
            }
            return 0;
        }
        // The game's load request for a pack entry's handle, or 0.
        uintptr_t Request(int32_t handle,uint64_t pack)
        {
            uintptr_t list=0,data=0; int32_t num=0;
            if(!Peek(Code::At(RequestList),list) || !list || !Peek(list+8,data) || !Peek(list+0x10,num)) return 0;
            for(int32_t i=0;i<num && i<1024;i++){
                uintptr_t r=0; int32_t h=0; uint64_t name=0;
                if(Peek(data+i*8,r) && r && Peek(r+8,h) && h==handle && Peek(r+0x10,name) && name==pack) return r;
            }
            return 0;
        }
        // The request's engine ids (at most 16).
        std::vector<int32_t> Ids(uintptr_t request)
        {
            std::vector<int32_t> ids;
            uintptr_t data=0; int32_t num=0;
            if(!Peek(request+0x38,data) || !Peek(request+0x40,num)) return ids;
            for(int32_t i=0;i<num && i<16;i++){ int32_t id=0; if(Peek(data+i*4,id)) ids.push_back(id); }
            return ids;
        }
        // For Stall: every pack entry of the pop manager's pack map (party
        // members' weapons and avatars as well as enemies) that is loading
        // (+0x48 == 2), with its handle and the game request's engine ids, each
        // marked pending or done. Hang 4's were party packs, between rounds, with
        // no territory armed, so the armed-territory listing in Tick missed them.
        void StuckPacks(std::ofstream& out,long long stamp)
        {
            Verify();
            uintptr_t g=0, pop=0, packs=0, pdata=0; int32_t pnum=0;
            Peek(Code::At(FieldGlobal),g);
            if(g) Peek(g+0x180,pop);
            if(pop) Peek(pop+0x18,packs);
            if(!packs || !Peek(packs+0xf0,pdata) || !Peek(packs+0xf8,pnum) || !pdata){ out<<stamp<<"\tpacks_loading\tno_pack_map\n"; return; }
            std::vector<uintptr_t> seen;
            int listed=0, loading=0;
            for(int32_t i=0;i<pnum && i<8192;i++){
                uintptr_t value=0, entries=0; int32_t n=0;
                if(!Peek(pdata+i*0x18+8,value) || !value || !Peek(value,entries) || !Peek(value+8,n) || !entries) continue;
                for(int32_t j=0;j<n && j<32;j++){
                    uintptr_t p=0; int32_t st=-1, handle=0; uint64_t pname=0;
                    if(!Peek(entries+j*8,p) || !p || !Peek(p+0x48,st) || st!=2) continue;
                    if(std::find(seen.begin(),seen.end(),p)!=seen.end()) continue;
                    seen.push_back(p);
                    loading++;
                    if(listed>=16) continue;
                    listed++;
                    uint64_t key=0; Peek(pdata+i*0x18,key);
                    Peek(p+4,pname); Peek(p+0x44,handle);
                    out<<stamp<<"\tpack_loading\t"<<Text(key)<<"\t"<<Text(pname)<<"\thandle="<<handle<<"\tpending="<<Pending(handle);
                    if(const uintptr_t r=Request(handle,pname)){
                        out<<"\tids=";
                        bool first=true;
                        for(int32_t id:Ids(r)){ out<<(first?"":",")<<id<<":"<<Pending(id); first=false; }
                    }else out<<"\trequest=none";
                    out<<"\n";
                }
            }
            out<<stamp<<"\tpacks_loading\t"<<loading<<"\tmap="<<pnum<<"\n";
        }
        struct Waiting { int32_t handle; ULONGLONG since; bool tried; };
        std::unordered_map<uintptr_t,Waiting> waiting;   // pack entry at state 2 -> since when, on which handle
        struct Rooted { RC::Unreal::UObject* object; int32_t index; ULONGLONG until; };
        std::vector<Rooted> rooted;
        bool on=false;
        // Unroot objects the recovery loaded, after RootFor (the spawned
        // characters hold them by then), if the slot still holds that object.
        void Release(ULONGLONG now)
        {
            for(auto it=rooted.begin();it!=rooted.end();){
                if(now<it->until){ ++it; continue; }
                try {
                    RC::Unreal::UObjectGlobals::ForEachUObjectInRange(it->index,it->index,[&](RC::Unreal::UObject* object,int32_t,int32_t){
                        if(object==it->object) object->ClearRootSet();
                        return RC::LoopAction::Break;
                    });
                } catch(...) {}
                it=rooted.erase(it);
            }
        }
        std::vector<std::wstring> PathsFor(const std::string& pack)
        {
            std::vector<std::wstring> out;
            std::ifstream in(Dev("junon-spawnfix-paths.tsv"));
            std::string line;
            while(std::getline(in,line)){
                while(!line.empty() && (line.back()=='\r' || line.back()==' ')) line.pop_back();
                const auto tab=line.find('\t');
                if(tab==std::string::npos || line.compare(0,tab,pack)!=0 || tab!=pack.size()) continue;
                const std::string path=line.substr(tab+1);
                if(path.rfind("/Game/",0)==0 && path.find('.')!=std::string::npos && out.size()<32) out.emplace_back(path.begin(),path.end());
            }
            return out;
        }
        bool WriteLoaded(uintptr_t entry)
        {
            __try { *reinterpret_cast<volatile int32_t*>(entry+0x44)=-1; *reinterpret_cast<volatile int32_t*>(entry+0x48)=3; return true; }
            __except(1) { return false; }
        }
        void Fix(std::ofstream& out,long long stamp,uintptr_t entry,int32_t step,uintptr_t packs,bool loaderKnown,int32_t queued,int32_t inFlight,ULONGLONG now)
        {
            auto& w=waiting[entry];
            if(w.tried || now-w.since<FixAfter) return;
            w.tried=true;   // from here on, once per entry
            int32_t type=-1, handle=0, st=-1; uint64_t name=0; uintptr_t owner=0;
            Peek(entry,type); Peek(entry+4,name); Peek(entry+0x38,owner); Peek(entry+0x44,handle); Peek(entry+0x48,st);
            const std::string pack=Text(name);
            auto refuse=[&](const std::string& why){ out<<stamp<<"\tfix_refused\t"<<pack<<"\t"<<why<<"\n"; Event("spawn_stall_fix_refused ",why.c_str()); };
            if(state!=1) return refuse("code_checks_unverified");
            if(step!=2) return refuse("sequence_not_waiting_for_spawns step="+std::to_string(step));
            if(!loaderKnown) return refuse("engine_loader_unverified");
            if(queued!=0 || inFlight!=0) return refuse("engine_loader_not_idle queued="+std::to_string(queued)+" in_flight="+std::to_string(inFlight));
            if(type!=1 || owner!=packs || st!=2 || handle!=w.handle) return refuse("entry_changed");
            if(pack.rfind("CharaSpec_",0)!=0) return refuse("not_a_charaspec_pack");
            if(Pending(handle)!="1") return refuse("handle_not_pending");
            const uintptr_t request=Request(handle,name);
            if(!request) return refuse("request_not_found");
            const auto ids=Ids(request);
            if(ids.empty()) return refuse("request_has_no_engine_ids");
            for(int32_t id:ids) if(Pending(id)!="1") return refuse("engine_request_not_pending "+std::to_string(id));
            const auto paths=PathsFor(pack);
            if(paths.empty()) return refuse("no_asset_paths_listed");
            for(const auto& path:paths){
                const std::string narrow=Stall::Narrow(path);
                out<<stamp<<"\tfix_load\t"<<pack<<"\t"<<narrow<<"\n";
                RC::Unreal::UObject* loaded=nullptr;
                try {
                    std::ofstream trace(Dev("junon-spawnfix-load.tsv"),std::ios::app);
                    trace<<"load\t"<<narrow<<"\n";
                    loaded=LoadAssetPath(path.c_str(),trace);
                } catch(...) { loaded=nullptr; }
                if(!loaded) return refuse("load_failed "+narrow);
                int32_t index=-1;
                try { index=loaded->GetInternalIndex(); loaded->SetRootSet(); } catch(...) { return refuse("root_failed "+narrow); }
                rooted.push_back({loaded,index,now+RootFor});
                RC::Unreal::UObject* found=nullptr;
                try { found=RC::Unreal::UObjectGlobals::StaticFindObject<RC::Unreal::UObject*>(nullptr,nullptr,path.c_str()); } catch(...) { found=nullptr; }
                if(found!=loaded) return refuse("not_found_after_load "+narrow);
                out<<stamp<<"\tfix_resolved\t"<<narrow<<"\n";
            }
            int32_t handleNow=0, stateNow=-1;
            if(!Peek(entry+0x44,handleNow) || handleNow!=handle || !Peek(entry+0x48,stateNow) || stateNow!=2) return refuse("entry_changed_during_load");
            if(!WriteLoaded(entry)) return refuse("write_fault");
            out<<stamp<<"\tfix_marked_loaded\t"<<pack<<"\thandle="<<handle<<"\tassets="<<paths.size()<<"\n";
            Event("spawn_stall_","fix_marked_loaded");
        }
        // Game thread, at a safe point, once a second (FrameWork).
        void Tick()
        {
            if(GameBuild()!=SteamJan2025) return;   // dev diagnostics: old-build addresses only (not ported to 1.005)
            const auto now=GetTickCount64();
            if(!rooted.empty()) Release(now);
            const auto trigger=Dev("junon-spawnstall.on");
            std::error_code ec;
            if(trigger.empty() || !std::filesystem::exists(trigger,ec)){ on=false; waiting.clear(); return; }
            if(ArenaReady::state!=1) return;
            const bool verified=Verify();
            std::ofstream out(Dev("junon-spawnstall.tsv"),std::ios::app);
            const auto stamp=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            if(!on){ on=true; waiting.clear(); out<<stamp<<"\tspawn_stall_begin\tchecks="<<(verified?"verified":"unverified")<<"\n"; }
            int32_t s298=-1, s29c=-1;
            const uintptr_t sequence=ColosseumScan::Sequence();
            if(sequence){ Peek(sequence+0x298,s298); Peek(sequence+0x29c,s29c); }
            int32_t queued=-1, inFlight=-1; uint8_t suspended=0xff;
            const bool loader=Loader::Counters(queued,inFlight,suspended);
            out<<stamp<<"\tsequence\t"<<(sequence ? "+298="+std::to_string(s298)+"\t+29c="+std::to_string(s29c) : std::string("not_found_yet"))
               <<"\tloader\t"<<(loader ? "queued="+std::to_string(queued)+"\tin_flight="+std::to_string(inFlight)+"\tsuspended="+std::to_string(suspended) : std::string("unverified"))<<"\n";
            uintptr_t g=0, pop=0, server=0, packs=0, sdata=0, pdata=0; int32_t snum=0, pnum=0;
            Peek(Code::At(FieldGlobal),g);
            if(g) Peek(g+0x180,pop);
            if(pop){ Peek(pop+0x10,server); Peek(pop+0x18,packs); }
            if(server){ Peek(server+8,sdata); Peek(server+0x10,snum); }
            if(packs){ Peek(packs+0xf0,pdata); Peek(packs+0xf8,pnum); }
            const uintptr_t o=ArenaReady::ArmedTerritory();
            if(!o){ out<<stamp<<"\tterritory\tnone_armed\n"; return; }
            int32_t count=0; uintptr_t spawns=0;
            Peek(o+0xd610,count);
            if(!Peek(o+0xd600,spawns) || !spawns) spawns=o+0xbf80;
            std::vector<uintptr_t> stuck;
            for(int k=0;k<count && k<32;k++){
                const uintptr_t e=spawns+k*0xf0;
                uint64_t name=0; int32_t st=-1;
                Peek(e,name); Peek(e+0x10,st);
                out<<stamp<<"\tspawn\t"<<k<<"\t"<<Text(name)<<"\tstate="<<st;
                const uintptr_t record=sdata ? Lookup(sdata,snum,name) : 0;
                if(record) out<<"\trecord+1ac="<<Stall::Field<int32_t>(record+0x1ac)<<"\tprio="<<Stall::Field<int32_t>(record+0x44)
                              <<"\tflags="<<Stall::Hex([&]{ uint32_t v=0; Peek(record+0x118,v); return v; }());
                else out<<"\trecord=none";
                out<<"\n";
                const uintptr_t value=pdata ? Lookup(pdata,pnum,name) : 0;
                uintptr_t entries=0; int32_t n=0;
                if(value){ Peek(value,entries); Peek(value+8,n); }
                for(int j=0;j<n && j<16;j++){
                    uintptr_t p=0;
                    if(!Peek(entries+j*8,p) || !p) continue;
                    int32_t type=-1, handle=0, pst=-1; uint64_t pname=0; uintptr_t owner=0;
                    Peek(p,type); Peek(p+4,pname); Peek(p+0x38,owner); Peek(p+0x44,handle); Peek(p+0x48,pst);
                    out<<stamp<<"\tpack\t"<<k<<"\t"<<Text(pname)<<"\ttype="<<type<<"\tstate="<<pst<<"\thandle="<<handle<<"\towner_ok="<<(owner==packs);
                    if(pst==2){
                        out<<"\tpending="<<Pending(handle);
                        if(const uintptr_t r=Request(handle,pname)){
                            out<<"\tids=";
                            bool first=true;
                            for(int32_t id:Ids(r)){ out<<(first?"":",")<<id<<":"<<Pending(id); first=false; }
                        }else out<<"\trequest=none";
                        auto it=waiting.find(p);
                        if(it==waiting.end() || it->second.handle!=handle) it=waiting.insert_or_assign(p,Waiting{handle,now,false}).first;
                        out<<"\twaiting_s="<<(now-it->second.since)/1000;
                        stuck.push_back(p);
                    }
                    out<<"\n";
                }
            }
            for(auto it=waiting.begin();it!=waiting.end();)
                if(std::find(stuck.begin(),stuck.end(),it->first)==stuck.end()) it=waiting.erase(it); else ++it;
            if(!stuck.empty() && DevFlag("junon-spawnfix.on"))
                for(uintptr_t p:stuck) Fix(out,stamp,p,s29c,packs,loader,queued,inFlight,now);
        }
    }

    // ---- Helper work at a safe point (2026-11-11) ----
    // Hang 3 (2026-11-10): the engine lost two package requests while its
    // loader sat idle, in a session where the helper did engine work from
    // arbitrary game-thread ProcessEvent calls (StaticFindObject, object scans,
    // level and asset loads, party-data calls), which can sit inside async-load
    // completion callbacks or level streaming's update. So all of it now runs
    // at a SafePoint (a Blueprint tick or camera update: inside UWorld::Tick's
    // gameplay phase), one unit of work per frame: a queued level or mesh
    // request, else the first due periodic job in turn. While the package
    // loader has packages queued or in flight (Loader::Busy, verified), work
    // waits, but never longer than MaxDefer, so nothing starves during long
    // streaming. Garbage collection runs on the game thread between frames,
    // never inside UWorld::Tick, so a safe point is never inside it; there is no
    // separate check (no verified IsGarbageCollecting global either).
    // Liveness: if no safe point has come for FallbackAfter (a paused game
    // ticks no Blueprints; a loading screen may not either), the periodic jobs
    // (never a load) run from every 256th game-thread call, as before, and the
    // event log says so; queued requests then wait or expire to Deferred.
    namespace FrameWork
    {
        struct Job { const char* name; ULONGLONG period; void(*run)(); ULONGLONG next; };
        Job jobs[]={
            {"arena_ready",250,ArenaReady::Tick,0},
            {"round_shuffle",1000,RoundShuffle::Tick,0},
            {"infusions",250,InfusionSkills::Tick,0},
            {"stall",1000,Stall::Tick,0},
            {"spawn_stall",1000,SpawnStall::Tick,0},
        };
        constexpr ULONGLONG MaxDefer=1500, FallbackAfter=1000;   // ms
        size_t cursor=0;
        ULONGLONG lastSafe=0, statsAt=0;
        bool fallback=false;
        struct Stats { uint32_t jobs=0, served=0, fallbackJobs=0, waitedForLoader=0, forcedWhileLoading=0; } stats;
        // The first due job in turn (round robin), or null.
        Job* Next(ULONGLONG now,bool loading)
        {
            for(size_t i=0;i<std::size(jobs);i++){
                Job& j=jobs[(cursor+i)%std::size(jobs)];
                if(now<j.next) continue;
                if(loading && j.next && now-j.next<MaxDefer){ stats.waitedForLoader++; continue; }
                if(loading) stats.forcedWhileLoading++;
                cursor=(cursor+i+1)%std::size(jobs);
                return &j;
            }
            return nullptr;
        }
        void Run(Job& j,ULONGLONG now)
        {
            j.next=now+j.period;
            stats.jobs++;
            try { j.run(); } catch(...) {}
        }
        // Once a minute, what ran where (event log).
        void Report(ULONGLONG now)
        {
            if(now-statsAt<60000) return;
            if(statsAt){
                std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app)
                    <<"frame_work jobs="<<stats.jobs<<" served="<<stats.served<<" fallback_jobs="<<stats.fallbackJobs
                    <<" waited_for_loader="<<stats.waitedForLoader<<" forced_while_loading="<<stats.forcedWhileLoading
                    <<" loader_check="<<(Loader::state==1?"verified":"off")<<"\n";
            }
            statsAt=now; stats={};
        }
    }
    // A queued request, served at this safe point (one per frame).
    bool ServeOneQueued(const char* kind,RC::Unreal::UFunction* via,bool loading)
    {
        Queue::Entry e{};
        if(!Queue::TakeOne(e,loading?FrameWork::MaxDefer:0)) return false;
        ServeEntry(e,kind,via);
        return true;
    }
    // Every game-thread ProcessEvent: expire old queued requests (every 100 ms)
    // and, at a safe point with the gate open, do one unit of helper work.
    void AtGameThreadCall(RC::Unreal::UObject* object,RC::Unreal::UFunction* function)
    {
        thread_local bool busy=false;   // our loads re-enter ProcessEvent
        if(busy) return;
        const auto now=GetTickCount64();
        const char* kind=SafePoint::Kind(function);
        if(kind){
            FrameWork::lastSafe=now;
            if(FrameWork::fallback){ FrameWork::fallback=false; Event("frame_work_","safe_point_back"); }
            if(!SafePoint::Open(object,function)) return;
        }else{
            if(now-FrameWork::lastSafe<FrameWork::FallbackAfter) return;
            static uint32_t calls=0;
            if((++calls&255)!=0) return;
            if(!FrameWork::fallback){ FrameWork::fallback=true; Event("frame_work_","fallback_no_safe_point"); }
        }
        busy=true;
        try {
            static ULONGLONG nextExpiry=0;
            if(Queue::any.load(std::memory_order_acquire) && now>=nextExpiry){ nextExpiry=now+100; ExpireQueued(); }
            const bool loading=Loader::Busy();
            bool worked=false;
            if(kind && Queue::any.load(std::memory_order_acquire) && ServeOneQueued(kind,function,loading)){ worked=true; FrameWork::stats.served++; }
            if(!worked)
                if(auto* job=FrameWork::Next(now,loading)){
                    FrameWork::Run(*job,now);
                    worked=true;
                    if(!kind) FrameWork::stats.fallbackJobs++;
                }
            if(worked && kind) SafePoint::Close(object,function);
            FrameWork::Report(now);
        } catch(...) {}
        busy=false;
    }

    class JunonColosseumNative : public RC::CppUserModBase
    {
    public:
        JunonColosseumNative()
        {
            ModName = STR("Junon Colosseum native identity");
            ModVersion = STR("0.1.0");
            ModDescription = STR("Names the custom deferred noticeboard before native registration; gives the party accessory infusions");
            ModAuthors = STR("CaitGPT");
        }
        void on_unreal_init() override
        {
            auto* tick = RC::Unreal::UObjectGlobals::StaticFindObject<RC::Unreal::UFunction*>(nullptr,nullptr,STR("/Script/Engine.Actor:SetActorTickEnabled"));
            ColosseumScan::Start();
            Watch::Start();
            Trace::Start();
            if (!tick) return;
            SafePoint::Init();
            RC::Unreal::Hook::RegisterProcessEventPreCallback([tick](auto* object,auto* function,void*) {
                Probe(function);
                // Table edits, party data and loads only on the game thread (see OnGameThread).
                const bool game=OnGameThread();
                if(game) InfusionSkills::Event(object,function);   // a name compare: notes a new world
                // All other helper engine work: one unit per frame at a safe point (FrameWork).
                if(game) { try { AtGameThreadCall(object,function); } catch(...) {} }
                // Requests are only renamed and queued here; the noticeboard must be
                // named now, before its deferred spawn finishes.
                if (function==tick) { RequestOwnedLevel(object);RequestBoardMesh(object);RenameBoard(object); }
            });
            std::ofstream(Dev("junon-native-identity-events.log"),std::ios::app) << "game_thread_identity_hook_ready\n";
        }
    };
}
extern "C" __declspec(dllexport) RC::CppUserModBase* start_mod() { return new JunonColosseumNative(); }
extern "C" __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod) { delete mod; }
