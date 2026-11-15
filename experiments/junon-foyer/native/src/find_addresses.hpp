#pragma once
// Finding the game's own code on a build we have never measured.
//
// This helper used to carry absolute addresses per game build, so a player on any
// other build - the Steam copy of 1.005, say - had every feature switched off and
// no noticeboard. Nothing here is build-specific: a byte pattern locates an
// instruction, the executable's own .pdata table turns that into the function it
// belongs to, and the remaining addresses follow from the game's own operands.
//
// Each pattern was generated from one of our two builds and then required to match
// exactly once in the other, at the address that build's table already named, so it
// has already survived a full recompilation of the game.
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <vector>

namespace Find
{
    inline const uint8_t* Base()
    {
        static const auto* base=reinterpret_cast<const uint8_t*>(GetModuleHandleW(nullptr));
        return base;
    }
    inline const IMAGE_NT_HEADERS64* Nt()
    {
        const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(Base());
        return reinterpret_cast<const IMAGE_NT_HEADERS64*>(Base()+dos->e_lfanew);
    }
    // The executable's code, where every function we look for lives.
    struct Region { uintptr_t rva; size_t size; };
    inline Region Text()
    {
        static const Region text=[]()->Region{
            const auto* nt=Nt();
            const auto* section=IMAGE_FIRST_SECTION(nt);
            for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i,++section)
                if(!std::memcmp(section->Name,".text",5))
                    return {section->VirtualAddress,section->Misc.VirtualSize};
            return {0,0};
        }();
        return text;
    }

    // "48 89 ?? 24" -> bytes, with -1 for a wildcard.
    inline std::vector<int> Parse(const char* pattern)
    {
        std::vector<int> out;
        for(const char* p=pattern;*p;)
        {
            if(*p==' '){++p;continue;}
            if(*p=='?'){out.push_back(-1); while(*p=='?')++p; continue;}
            out.push_back(int(std::strtoul(p,nullptr,16)));
            while(*p && *p!=' ')++p;
        }
        return out;
    }
    // The one place in the code where the pattern matches, as an RVA, or 0 for
    // none or more than one. Ambiguity is always refused: a wrong address is far
    // worse than a feature that stays off and says so.
    inline uintptr_t UniqueInText(const char* pattern)
    {
        const std::vector<int> want=Parse(pattern);
        if(want.empty() || want[0]<0) return 0;
        const Region text=Text();
        if(!text.size || want.size()>text.size) return 0;
        const uint8_t* const start=Base()+text.rva;
        const uint8_t* const last=start+text.size-want.size();
        const uint8_t first=uint8_t(want[0]);
        uintptr_t found=0;
        for(const uint8_t* p=start;p<=last;)
        {
            // memchr is far faster than stepping byte by byte over 100 MB.
            p=static_cast<const uint8_t*>(std::memchr(p,first,size_t(last-p)+1));
            if(!p) break;
            size_t i=1;
            for(;i<want.size();++i)
                if(want[i]>=0 && p[i]!=uint8_t(want[i])) break;
            if(i==want.size())
            {
                if(found) return 0;                 // a second match: refuse
                found=text.rva+uintptr_t(p-start);
            }
            ++p;
        }
        return found;
    }

    // Every place the pattern matches, for patterns that are not meant to be unique.
    inline std::vector<uintptr_t> AllInText(const char* pattern)
    {
        std::vector<uintptr_t> out;
        const std::vector<int> want=Parse(pattern);
        if(want.empty() || want[0]<0) return out;
        const Region text=Text();
        if(!text.size || want.size()>text.size) return out;
        const uint8_t* const start=Base()+text.rva;
        const uint8_t* const last=start+text.size-want.size();
        const uint8_t first=uint8_t(want[0]);
        for(const uint8_t* p=start;p<=last;)
        {
            p=static_cast<const uint8_t*>(std::memchr(p,first,size_t(last-p)+1));
            if(!p) break;
            size_t i=1;
            for(;i<want.size();++i)
                if(want[i]>=0 && p[i]!=uint8_t(want[i])) break;
            if(i==want.size()) out.push_back(text.rva+uintptr_t(p-start));
            ++p;
        }
        return out;
    }

    // Does the pattern sit at exactly this address?
    inline bool MatchesAt(uintptr_t rva,const char* pattern)
    {
        const std::vector<int> want=Parse(pattern);
        if(want.empty()) return false;
        const Region text=Text();
        if(rva<text.rva || rva+want.size()>text.rva+text.size) return false;
        const uint8_t* at=Base()+rva;
        for(size_t i=0;i<want.size();++i)
            if(want[i]>=0 && at[i]!=uint8_t(want[i])) return false;
        return true;
    }

    // The function an address belongs to, from the executable's exception table.
    inline uintptr_t FunctionOf(uintptr_t rva)
    {
        const auto& dir=Nt()->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
        if(!dir.VirtualAddress || !dir.Size) return 0;
        const auto* table=reinterpret_cast<const RUNTIME_FUNCTION*>(Base()+dir.VirtualAddress);
        size_t count=dir.Size/sizeof(RUNTIME_FUNCTION);
        size_t low=0,high=count;
        while(low<high)
        {
            const size_t mid=(low+high)/2;
            if(table[mid].BeginAddress<=rva) low=mid+1; else high=mid;
        }
        if(!low) return 0;
        const auto& fn=table[low-1];
        return (rva>=fn.BeginAddress && rva<fn.EndAddress) ? fn.BeginAddress : 0;
    }

    // Where a RIP-relative instruction points: its displacement sits dispAt bytes
    // in, and is counted from the end of an instruction length bytes long.
    inline uintptr_t Rip(uintptr_t rva,int dispAt,int length)
    {
        int32_t displacement=0;
        std::memcpy(&displacement,Base()+rva+dispAt,4);
        return uintptr_t(int64_t(rva)+length+displacement);
    }

    // A function's whole extent, from the exception table.
    inline bool FunctionExtent(uintptr_t rva,uintptr_t& begin,uintptr_t& end)
    {
        const auto& dir=Nt()->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
        if(!dir.VirtualAddress || !dir.Size) return false;
        const auto* table=reinterpret_cast<const RUNTIME_FUNCTION*>(Base()+dir.VirtualAddress);
        size_t low=0,high=dir.Size/sizeof(RUNTIME_FUNCTION);
        while(low<high)
        {
            const size_t mid=(low+high)/2;
            if(table[mid].BeginAddress<=rva) low=mid+1; else high=mid;
        }
        if(!low) return false;
        const auto& fn=table[low-1];
        if(rva<fn.BeginAddress || rva>=fn.EndAddress) return false;
        begin=fn.BeginAddress; end=fn.EndAddress;
        return true;
    }

    // Every direct call in a function's first `span` bytes, with where each one is.
    inline std::vector<std::pair<uintptr_t,uintptr_t>> CallSitesIn(uintptr_t rva,size_t span)
    {
        std::vector<std::pair<uintptr_t,uintptr_t>> out;
        const uint8_t* body=Base()+rva;
        for(size_t i=0;i+5<=span;++i)
            if(body[i]==0xE8)
            {
                int32_t rel=0;
                std::memcpy(&rel,body+i+1,4);
                out.push_back({i,uintptr_t(int64_t(rva)+int64_t(i)+5+rel)});
            }
        return out;
    }

    // Every direct call in a function's first `span` bytes.
    inline std::vector<uintptr_t> CallsIn(uintptr_t rva,size_t span)
    {
        std::vector<uintptr_t> out;
        const uint8_t* body=Base()+rva;
        for(size_t i=0;i+5<=span;++i)
            if(body[i]==0xE8)
            {
                int32_t rel=0;
                std::memcpy(&rel,body+i+1,4);
                out.push_back(uintptr_t(int64_t(rva)+int64_t(i)+5+rel));
            }
        return out;
    }

    // Every place in the image holding this 8-byte value on an 8-byte boundary.
    inline std::vector<uintptr_t> QwordsEqual(uint64_t value)
    {
        std::vector<uintptr_t> out;
        const auto* nt=Nt();
        const auto* section=IMAGE_FIRST_SECTION(nt);
        for(unsigned s=0;s<nt->FileHeader.NumberOfSections;++s,++section)
        {
            const uintptr_t rva=section->VirtualAddress;
            const size_t size=section->Misc.VirtualSize;
            if(size<8) continue;
            const uint8_t* data=Base()+rva;
            for(size_t i=0;i+8<=size;i+=8)
            {
                uint64_t here=0;
                std::memcpy(&here,data+i,8);
                if(here==value) out.push_back(rva+i);
            }
        }
        return out;
    }
}
