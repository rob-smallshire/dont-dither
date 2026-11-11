\ ============================================================================
\ spitfire.asm -- asking SPItFIRE what joysticks it has
\
\ Shared by SPLASH (which says on the title screen what it found) and DITHER
\ (which plays with the joysticks: joystick.asm). SPItFIRE is a Master
\ Compact peripheral with its own sideways ROM; this uses only the ROM's
\ documented interface (the SPItFIRE repository's
\ docs/joystick-programming.md), as tools/dontdither/joysticks.py models it.
\
\ OSWORD &3F with reason code 0 in byte 0 of the block: SPItFIRE answers by
\ setting byte 0 to &53 ("S"); byte 4 is the number of joysticks allocated,
\ bytes 6-9 are joysticks 1-4's port (bit 7: 0 = A, 1 = B) and port type
\ (bits 0-2), &FF for one not allocated, and byte 10 holds flags (bit 0: no
\ workspace, the user must press Ctrl-Break; bit 1: the hardware did not
\ answer). Without SPItFIRE nothing claims the call and the block comes
\ back unchanged, byte 0 still 0: a Model B, or a Compact without it, has
\ no joysticks.
\
\ Requires: os.asm, spitfire_data.asm (generated), and spitfire_block
\ (SPITFIRE_BLOCK_BYTES bytes) defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ ask_spitfire -- fill spitfire_block with SPItFIRE's description, if fitted
\
\ On exit:   spitfire_block byte 0 = SPITFIRE_SIGNATURE if SPItFIRE answered,
\            else 0; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.ask_spitfire
    LDA #0                     \ Reason code 0: describe the joysticks.
    STA spitfire_block         \ (Also byte 0: stays 0 if nothing answers.)
    LDA #OSWORD_SPITFIRE
    LDX #LO(spitfire_block)
    LDY #HI(spitfire_block)
    JMP OSWORD                 \ Tail call.

\ ----------------------------------------------------------------------------
\ count_joysticks -- how many of SPItFIRE's joysticks the game can use
\
\ On entry:  spitfire_block filled by ask_spitfire
\ On exit:   X = 0-4: 0 unless SPItFIRE answered, is ready (no flags), and
\            allocated some (joysticks.joysticks_available); A corrupted
\ ----------------------------------------------------------------------------

.count_joysticks
    LDX #0                     \ None, unless...
    LDA spitfire_block
    CMP #SPITFIRE_SIGNATURE    \ ...SPItFIRE answered...
    BNE count_joysticks_done
    LDA spitfire_block + SPITFIRE_FLAGS
    BNE count_joysticks_done   \ ...and is ready (no Ctrl-Break needed, the
    LDX spitfire_block + SPITFIRE_COUNT   \ hardware answering).
    CPX #SPITFIRE_MAX_JOYSTICKS + 1   \ (At most four; anything more is not
    BCC count_joysticks_done          \ ours.)
    LDX #SPITFIRE_MAX_JOYSTICKS
.count_joysticks_done
    RTS
