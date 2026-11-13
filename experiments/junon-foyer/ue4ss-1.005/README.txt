UE4SS settings for FINAL FANTASY VII REBIRTH 1.005 (optional)

On game version 1.005, UE4SS 3.0.1 (RE-UE4SS FF7R 1.0.2, Nexus mod 267) stops at
start-up and runs no mods. These are the two changes we made and tested with, on the
Epic Games Store version of 1.005. The optional 1.005 file on mod 267's Files tab is
another way to fix this; use one or the other, not both. Back up your ue4ss folder first.

1. Copy the ue4ss folder from this zip into End\Binaries\Win64\. It replaces
   ue4ss\UE4SS_Signatures\FText_Constructor.lua with one that finds FText's
   constructor by its first instructions (the old pattern no longer matches).

2. Open End\Binaries\Win64\ue4ss\VTableLayout.ini in a text editor. In the [UObject]
   section, find the line FinishDestroy and add a new line below it:

       unk_2

   so that it reads FinishDestroy, unk_2, then the Serialize lines. Version 1.005 added
   one virtual function there, and every later entry moved down by one. Save the file.

To undo: restore your backup.
These settings are not needed on the January 2025 version of the game.
