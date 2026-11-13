-- FText::FText(FString&&) for the Epic Games build of FINAL FANTASY VII REBIRTH
-- ff7rebirth_.exe sha256 73d13281072fa54d8fdcae8323bd76dbf6c2662c37e0d3a2f2b61ac2eb60168c
--
-- The signature that ships with UE4SS matches a CALL SITE and resolves the call. That call
-- site no longer exists in this build (0 matches), which is why UE4SS v3.0.1 aborts with
-- "FText_Constructor.lua did not return a valid address for FText::FText".
--
-- This pattern is anchored on the FUNCTION ENTRY instead, so OnMatchFound returns the match
-- address unchanged. Call-displacement bytes are wildcarded; everything else is literal.
--
--   48 89 5C 24 10              mov   [rsp+10h], rbx
--   57                          push  rdi
--   B8 60 00 00 00              mov   eax, 60h
--   E8 ?? ?? ?? ??              call  __chkstk
--   48 2B E0                    sub   rsp, rax
--   83 7A 08 01                 cmp   dword ptr [rdx+8], 1     ; FString::ArrayNum <= 1 ?
--   48 8B F9                    mov   rdi, rcx                 ; rcx = FText* this
--   C7 44 24 70 00 00 00 00     mov   dword ptr [rsp+70h], 0
--   7E ??                       jle   <empty-text path>
--   48 8D 4C 24 20              lea   rcx, [rsp+20h]
--
-- Matches exactly once in the whole module image (base .. base+SizeOfImage),
-- at .text RVA 0x120773C, i.e. default-base runtime address 0x14120773C.
-- That address is a .pdata function entry (0x120773C..0x1207809) with 144 call sites.

function Register()
    return "48 89 5C 24 10 57 B8 60 00 00 00 E8 ?? ?? ?? ?? 48 2B E0 83 7A 08 01 48 8B F9 C7 44 24 70 00 00 00 00 7E ?? 48 8D 4C 24 20"
end

function OnMatchFound(matchAddress)
    -- The pattern starts at the function's first instruction, so no call has to be resolved.
    return matchAddress
end
