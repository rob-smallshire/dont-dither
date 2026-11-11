\ ============================================================================
\ fake_spitfire.asm -- a test double for the SPItFIRE ROM's joystick interface
\
\ Beebium emulates neither a Master Compact nor SPItFIRE, so the joystick
\ tests run the game on a Model B with this standing in for SPItFIRE. It
\ answers what the game uses of the documented interface (the SPItFIRE
\ repository's docs/joystick-programming.md):
\
\   OSWORD &3F  reasons 0-3 (identify, summary, describe joystick j, name a
\               port type), from the configuration below -- or, if
\               cfg_present is 0, not at all, as a machine without SPItFIRE
\               (the block comes back unchanged). Unknown reasons are not
\               claimed either.
\   OSBYTE &80  channels 12 and 28, the switch bytes, from cfg_switches;
\               other channels and calls pass on.
\
\ Two parts, as on the real thing:
\
\ - A sideways ROM (assembled at &8000, saved as build/fake_spitfire.rom),
\   which the tests put in a spare slot when they launch the machine. Like
\   SPItFIRE's ROM, it claims OSWORD &3F through service call 8
\   (unrecognised OSWORD: the call's A in &EF, X and Y -- the block's
\   address -- in &F0 and &F1), and knows the port types' keywords
\   (build/fake_spitfire_names.asm, written by the tests from their
\   table).
\
\ - Its configuration and an OSBYTE hook in main RAM at &0880-&08FF (the
\   MOS's printer buffer and envelope storage, which the game never uses),
\   which the tests poke: what reasons 0-2 answer, the switch bytes, and
\   the previous BYTEV. RAM is zero at power-on, so the ROM stays silent
\   until a test sets cfg_present. A test that wants switch bytes copies
\   the hook in and points BYTEV at it.
\
\ It uses &A8-&AC (the MOS's transient workspace, as the real ROM uses
\ &A8-&AF) as pointers.
\
\ Assembled by tests/test_joysticks.py.
\ ============================================================================

\ ---- The configuration and hook, in main RAM --------------------------------

ORG &0880
GUARD &0900

.cfg_present  SKIP 1           \ Non-zero: answer OSWORD &3F.
.cfg_identify SKIP 5           \ Reason 0's bytes 1-5: API version, ROM
                               \ version (2), modules, status flags.
.cfg_summary  SKIP 8           \ Reason 1's bytes 1-8: n, port types (2),
                               \ joysticks 1-4, status flags.
.cfg_describe SKIP 16          \ Reason 2's bytes 2-5 for joysticks 1-4:
                               \ port/handset/type, kind, capabilities,
                               \ buttons.
.cfg_switches SKIP 4           \ Joysticks 1-4's switch bytes.
.cfg_old_bytev SKIP 2          \ BYTEV before byte_hook.

\ byte_hook: OSBYTE &80 on channel 12 or 28 answers the switch bytes,
\ joysticks 1 and 2 or 3 and 4, in X and Y. Anything else passes on.
.byte_hook
    CMP #&80
    BNE byte_pass
    CPX #12
    BEQ byte_12
    CPX #28
    BNE byte_pass
    LDX cfg_switches + 2       \ Joysticks 3 and 4.
    LDY cfg_switches + 3
    RTS
.byte_12
    LDX cfg_switches           \ Joysticks 1 and 2.
    LDY cfg_switches + 1
    RTS
.byte_pass
    JMP (cfg_old_bytev)
.hook_end

SAVE "build/fake_spitfire_hook.bin", byte_hook, hook_end

\ ---- The ROM ----------------------------------------------------------------

BLOCK     = &A8                \ The caller's OSWORD block.
BUFFER    = &AA                \ Reason 3: the caller's buffer...
ROOM      = &AC                \ ...and its size.
SIGNATURE = &53
NAME_BYTES = 8                 \ Each keyword in fake_names, CR-terminated.

ORG &8000
GUARD &C000

.rom_start
    EQUB 0, 0, 0               \ No language entry.
    JMP service                \ Service entry.
    EQUB &82                   \ A service ROM, 6502 code.
    EQUB copyright - rom_start
    EQUB 1                     \ Version.
    EQUS "Fake SPItFIRE"
.copyright
    EQUB 0
    EQUS "(C)Test", 0

\ service: claim service call 8 for OSWORD &3F when configured; leave
\ everything else (A, X, Y unchanged).
.service
    CMP #8
    BNE service_pass
    PHA
    TXA
    PHA
    TYA
    PHA
    LDA &EF                    \ The OSWORD number.
    CMP #&3F
    BNE service_decline
    LDA cfg_present
    BEQ service_decline        \ "Not fitted".
    LDA &F0                    \ The block.
    STA BLOCK
    LDA &F1
    STA BLOCK + 1
    LDY #0
    LDA (BLOCK),Y              \ The reason.
    BEQ reason_identify
    CMP #1
    BEQ reason_summary
    CMP #2
    BEQ reason_describe
    CMP #3
    BNE service_decline
    JMP reason_name
.service_decline               \ Not ours, or a reason we do not know.
    PLA
    TAY
    PLA
    TAX
    PLA
.service_pass
    RTS

.service_claim                 \ Answered: byte 0 = &53, and claim it.
    LDY #0
    LDA #SIGNATURE
    STA (BLOCK),Y
    PLA
    TAY
    PLA
    TAX
    PLA
    LDA #0
    RTS

\ Reason 0: bytes 1-5 from cfg_identify.
.reason_identify
    LDX #0
.reason_identify_byte
    INX
    TXA
    TAY                        \ Y = X: the block byte.
    LDA cfg_identify - 1,X
    STA (BLOCK),Y
    CPX #5
    BNE reason_identify_byte
    BEQ service_claim          \ (Always.)

\ Reason 1: bytes 1-8 from cfg_summary.
.reason_summary
    LDX #0
.reason_summary_byte
    INX
    TXA
    TAY
    LDA cfg_summary - 1,X
    STA (BLOCK),Y
    CPX #8
    BNE reason_summary_byte
    BEQ service_claim          \ (Always.)

\ Reason 2: joystick j (byte 1): bytes 2-5 from cfg_describe; for any j
\ but 1-4, &FF then zeros.
.reason_describe
    LDY #1
    LDA (BLOCK),Y              \ j
    SEC
    SBC #1
    CMP #4
    BCS reason_describe_none
    ASL A                      \ (j - 1) * 4: its entry.
    ASL A
    TAX
    LDY #2
.reason_describe_byte
    LDA cfg_describe,X
    STA (BLOCK),Y
    INX
    INY
    CPY #6
    BNE reason_describe_byte
    BEQ service_claim          \ (Always.)
.reason_describe_none
    LDY #2
    LDA #&FF
    STA (BLOCK),Y
    LDA #0
.reason_describe_zero
    INY
    STA (BLOCK),Y
    CPY #5
    BNE reason_describe_zero
    BEQ service_claim          \ (Always.)

\ Reason 3: the keyword (byte 2 = 0) of type byte 1, into the buffer at
\ bytes 3-4 of size byte 5, CR-terminated and cut to fit; byte 6 the
\ characters copied, byte 7 bit 0 set if there is no such name (the buffer
\ then just a CR). Only keywords are known here.
.reason_name
    LDY #3                     \ The buffer...
    LDA (BLOCK),Y
    STA BUFFER
    INY
    LDA (BLOCK),Y
    STA BUFFER + 1
    INY
    LDA (BLOCK),Y              \ ...and its size.
    STA ROOM
    LDY #2                     \ A keyword?
    LDA (BLOCK),Y
    BNE reason_name_unknown
    DEY                        \ A known type?
    LDA (BLOCK),Y
    CMP #FAKE_TYPES
    BCS reason_name_unknown
    ASL A                      \ Its keyword: type * NAME_BYTES.
    ASL A
    ASL A
    ASSERT NAME_BYTES = 8
    TAX
    LDA ROOM
    BEQ reason_name_empty      \ Room for nothing: copy nothing.
    LDY #0
.reason_name_char
    LDA fake_names,X
    CMP #13
    BEQ reason_name_end
    INY                        \ Room for this and the CR (Y + 1 < size)?
    CPY ROOM
    DEY                        \ (Carry kept.)
    BCS reason_name_end        \ No: cut here.
    STA (BUFFER),Y
    INX
    INY
    BNE reason_name_char       \ (Always.)
.reason_name_end
    LDA #13
    STA (BUFFER),Y
    TYA                        \ Characters copied.
    LDY #6
    STA (BLOCK),Y
    LDA #0                     \ Flags: a name.
    BEQ reason_name_flags      \ (Always.)
.reason_name_empty
    LDY #6
    STA (BLOCK),Y              \ (A = 0.) Nothing copied, but the name
    BEQ reason_name_flags      \ exists. (Always.)
.reason_name_unknown
    LDA ROOM
    BEQ reason_name_unknown_count   \ Room for nothing.
    LDY #0
    LDA #13                    \ Just a CR.
    STA (BUFFER),Y
.reason_name_unknown_count
    LDY #6
    LDA #0
    STA (BLOCK),Y              \ Nothing copied...
    LDA #1                     \ ...no such name.
.reason_name_flags
    LDY #7
    STA (BLOCK),Y
    JMP service_claim

\ fake_names: FAKE_TYPES keywords, NAME_BYTES each, CR-terminated (written
\ by the tests).
INCLUDE "build/fake_spitfire_names.asm"

.rom_end

SAVE "build/fake_spitfire.rom", rom_start, &C000
