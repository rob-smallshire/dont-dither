\ ============================================================================
\ fake_spitfire.asm -- a test double for the SPItFIRE ROM's joystick interface
\
\ Beebium emulates neither a Master Compact nor SPItFIRE, so the joystick
\ tests run the game on a Model B with this standing in for the ROM. It
\ answers exactly what the game uses of the documented interface (the
\ SPItFIRE repository's docs/joystick-programming.md):
\
\   OSWORD &3F  copies fake_block (11 bytes) into the caller's block -- or,
\               if fake_block's byte 0 is 0, passes the call on, as a
\               machine without SPItFIRE does (the block comes back
\               unchanged);
\   OSBYTE &80  with X = channel 0-20 returns fake_lo/fake_hi for it in X
\               (low) and Y (high); other channels and calls pass on.
\
\ Everything else goes to the previous handlers, kept in old_bytev and
\ old_wordv. The tests poke the code in, set old_bytev/old_wordv to BYTEV
\ and WORDV's contents, point the vectors at byte_hook and word_hook, and
\ then move the sticks and press the buttons by poking fake_lo/fake_hi.
\
\ It lives at &0880-&08FF, the MOS's printer buffer and envelope storage,
\ which the game never uses (it prints nothing and makes no ENVELOPEs). It
\ uses &A8-&A9 (the MOS's transient workspace, as the real ROM does) as a
\ pointer.
\
\ Assembled by tests/conftest.py to build/fake_spitfire.bin.
\ ============================================================================

ORG &0880
GUARD &0900

.fake_block   SKIP 11          \ OSWORD &3F's answer: &53, version, port
                               \ types, count, keypads, joysticks, flags.
.fake_lo      SKIP 21          \ ADVAL channels 0-20: low bytes...
.fake_hi      SKIP 21          \ ...and high bytes.
.old_bytev    SKIP 2           \ The handlers before ours.
.old_wordv    SKIP 2

.byte_hook
    CMP #&80                   \ OSBYTE &80 on one of our channels?
    BNE byte_pass
    CPX #21
    BCS byte_pass              \ (Negative channels too: they are >= &80.)
    LDY fake_hi,X
    LDA fake_lo,X
    TAX
    LDA #&80
    RTS
.byte_pass
    JMP (old_bytev)

.word_hook
    CMP #&3F                   \ OSWORD &3F, with a SPItFIRE to describe?
    BNE word_pass
    PHA
    LDA fake_block
    BEQ word_pass_pull         \ "Not fitted": pass it on.
    STX &A8
    STY &A9
    LDY #10
.word_copy
    LDA fake_block,Y
    STA (&A8),Y
    DEY
    BPL word_copy
    PLA
    RTS
.word_pass_pull
    PLA
.word_pass
    JMP (old_wordv)

.fake_end

SAVE "build/fake_spitfire.bin", fake_block, fake_end
