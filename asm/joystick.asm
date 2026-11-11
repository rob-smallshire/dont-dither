\ ============================================================================
\ joystick.asm -- joysticks through SPItFIRE
\
\ SPItFIRE (a Master Compact peripheral, with its own sideways ROM) provides
\ up to four analogue joysticks. This module uses only the ROM's documented
\ interface (the SPItFIRE repository's docs/joystick-programming.md); it
\ must match tools/dontdither/joysticks.py.
\
\ Detection, once at start-up, asks SPItFIRE through spitfire.asm (shared
\ with SPLASH, which shows what it found). Without SPItFIRE, or with it not
\ ready, there are no joysticks and the game is played on the keyboard alone.
\
\ Reading: OSBYTE &80 (ADVAL) with X = a channel returns its 16-bit value in
\ X (low) and Y (high). Joystick j (slot j-1: C, M, Y, K) has X and Y on
\ channels joystick_x_channels and _y_channels, and its fire button in the
\ low byte of channel joystick_fire_channels under joystick_fire_masks.
\ The ROM refreshes the values 50 times a second; reading them costs only
\ the call.
\
\ A stick points in a direction when it is more than a quarter of full
\ scale from the centre on that axis -- the high byte of the reading is
\ &C0 or more (X: left; Y: up) or below &40 (X: right; Y: down) -- so only
\ Y, the high byte, is looked at. The four direction bits are turned into a
\ direction through the keys' own table (key_direction).
\
\ Requires: os.asm, zeropage.asm, game_data.asm (the channel tables and
\ key_direction), spitfire.asm, and joysticks_available, joystick_slot,
\ joystick_buttons and spitfire_block defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ detect_joysticks -- set joysticks_available (0-4) from SPItFIRE, if fitted
\
\ On entry:  spitfire_block free (only at start-up: see main.asm)
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.detect_joysticks
    JSR ask_spitfire           \ Fills spitfire_block...
    JSR count_joysticks        \ ...X = the joysticks we can use.
    STX joysticks_available
    RTS

\ ----------------------------------------------------------------------------
\ joystick_input -- the input byte from player slot X's joystick
\
\ On entry:  X = slot (below joysticks_available)
\ On exit:   A = input byte (direction | FIRE_BIT); X, Y corrupted;
\            zp_keys corrupted
\ ----------------------------------------------------------------------------

.joystick_input
    STX joystick_slot
    LDA #0                     \ The direction bits: up 1, down 2, left 4,
    STA zp_keys                \ right 8, as the keys'.

    LDA joystick_y_channels,X  \ Y: up (high) or down (low)?
    JSR joystick_high_byte
    CMP #JOYSTICK_HIGH
    BCC joystick_input_not_up
    LDA #JOYSTICK_UP
    BNE joystick_input_y       \ (Always.)
.joystick_input_not_up
    CMP #JOYSTICK_LOW
    BCS joystick_input_x       \ Near the centre: neither.
    LDA #JOYSTICK_DOWN
.joystick_input_y
    STA zp_keys

.joystick_input_x
    LDX joystick_slot          \ X: left (high) or right (low)?
    LDA joystick_x_channels,X
    JSR joystick_high_byte
    CMP #JOYSTICK_HIGH
    BCC joystick_input_not_left
    LDA #JOYSTICK_LEFT
    BNE joystick_input_add_x   \ (Always.)
.joystick_input_not_left
    CMP #JOYSTICK_LOW
    BCS joystick_input_fire
    LDA #JOYSTICK_RIGHT
.joystick_input_add_x
    ORA zp_keys
    STA zp_keys

.joystick_input_fire
    LDX joystick_slot
    JSR joystick_fire          \ Z clear if fire is held.
    BEQ joystick_input_direction
    LDA #FIRE_BIT
.joystick_input_direction
    LDX zp_keys                \ Direction from the keys' table, plus fire.
    ORA key_direction,X
    RTS

\ joystick_high_byte: A = the high byte of ADVAL channel A. X, Y corrupted.
.joystick_high_byte
    TAX
    LDA #&80                   \ OSBYTE &80: read the channel; Y = high byte.
    JSR OSBYTE
    TYA
    RTS

\ ----------------------------------------------------------------------------
\ joystick_fire -- is player slot X's joystick fire button held?
\
\ On entry:  X = slot (below joysticks_available)
\ On exit:   A = non-zero (Z clear) if held, 0 if not; X, Y corrupted
\ ----------------------------------------------------------------------------

.joystick_fire
    LDA joystick_fire_masks,X
    PHA
    LDA joystick_fire_channels,X
    TAX
    LDA #&80                   \ OSBYTE &80: the buttons are in X, the low
    JSR OSBYTE                 \ byte (the high byte is not a button).
    PLA
    STX joystick_buttons
    AND joystick_buttons
    RTS
