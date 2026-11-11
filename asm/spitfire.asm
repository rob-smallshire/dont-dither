\ ============================================================================
\ spitfire.asm -- asking SPItFIRE what joysticks it has
\
\ Shared by SPLASH (which says on the title screen what it found) and DITHER
\ (which plays with the joysticks: joystick.asm). SPItFIRE is a Master
\ Compact peripheral with its own sideways ROM; this uses only the ROM's
\ documented interface (the SPItFIRE repository's
\ docs/joystick-programming.md), as tools/dontdither/joysticks.py models it.
\
\ OSWORD &3F, its reason code in byte 0 of the block. SPItFIRE answers by
\ setting byte 0 to &53 ("S"); without it -- or for a reason it does not
\ know -- nothing claims the call and the block comes back unchanged. So a
\ Model B, or a Compact without SPItFIRE, has no joysticks.
\
\   reason 0, identify: byte 5 the status flags (non-zero: not ready --
\             Ctrl-Break needed, the hardware not answering, joystick
\             handling off, or updates stopped);
\   reason 1, summary: byte 1 n, the joysticks (1 to n); bytes 4-7 each
\             one's port (bit 7), handset (bit 6) and port type (bits 0-5);
\   reason 2, describe joystick j (byte 1): byte 3 its kind (1: a stick),
\             byte 4 its capabilities (bit 1: its switch byte carries
\             directions).
\
\ A player can use joystick j if it is a stick with directions: SPItFIRE
\ says what each one is, so devices that are not sticks (a Bitstik's second
\ half, say) are left out without the game knowing any type numbers.
\
\ Requires: os.asm, spitfire_data.asm (generated), and spitfire_block
\ (SPITFIRE_BLOCK_BYTES bytes) defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ spitfire_call -- OSWORD &3F with reason A, on spitfire_block
\
\ On entry:  A = reason; spitfire_block's other entry bytes set
\ On exit:   spitfire_block as SPItFIRE left it; Z set if SPItFIRE answered
\            (byte 0 = SPITFIRE_SIGNATURE); A, X, Y corrupted
\ ----------------------------------------------------------------------------

.spitfire_call
    STA spitfire_block         \ The reason (left there if nobody answers).
    LDA #OSWORD_SPITFIRE
    LDX #LO(spitfire_block)
    LDY #HI(spitfire_block)
    JSR OSWORD
    LDA spitfire_block
    CMP #SPITFIRE_SIGNATURE
    RTS

\ ----------------------------------------------------------------------------
\ find_sticks -- which player slots can play on a SPItFIRE joystick
\
\ On exit:   A = a mask, bit j-1 set if joystick j is there and a stick with
\            directions; 0 unless SPItFIRE answered and is ready
\            (joysticks.stick_slots); X, Y corrupted; spitfire_block used
\ ----------------------------------------------------------------------------

.find_sticks
    LDA #0
    STA spitfire_sticks        \ None yet.
    LDA #SPITFIRE_IDENTIFY     \ Is it there...
    JSR spitfire_call
    BNE find_sticks_done
    LDA spitfire_block + SPITFIRE_FLAGS
    BNE find_sticks_done       \ ...and ready?
    LDA #SPITFIRE_SUMMARY      \ How many joysticks?
    JSR spitfire_call
    BNE find_sticks_done
    LDX spitfire_block + SPITFIRE_COUNT
    CPX #SPITFIRE_MAX_JOYSTICKS + 1   \ (At most four; anything more is not
    BCC find_sticks_count             \ ours.)
    LDX #SPITFIRE_MAX_JOYSTICKS
.find_sticks_count
    STX spitfire_j             \ Joysticks n down to 1:
.find_sticks_joystick
    LDA spitfire_j
    BEQ find_sticks_done
    STA spitfire_block + SPITFIRE_J
    LDA #SPITFIRE_DESCRIBE     \ What is joystick j?
    JSR spitfire_call
    BNE find_sticks_next
    LDA spitfire_block + SPITFIRE_KIND
    CMP #SPITFIRE_KIND_STICK
    BNE find_sticks_next       \ Not a stick.
    LDA spitfire_block + SPITFIRE_CAPABILITIES
    AND #SPITFIRE_HAS_DIRECTIONS
    BEQ find_sticks_next       \ No directions to steer by.
    LDX spitfire_j             \ Slot j-1 may use it: bit j-1.
    LDA stick_bits - 1,X
    ORA spitfire_sticks
    STA spitfire_sticks
.find_sticks_next
    DEC spitfire_j
    JMP find_sticks_joystick
.find_sticks_done
    LDA spitfire_sticks
    RTS

.stick_bits                    \ Joystick j's bit in the mask, j = 1-4.
    EQUB &01, &02, &04, &08
