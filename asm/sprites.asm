\ ============================================================================
\ sprites.asm -- drawing player tanks over the arena with save-under
\
\ Each player's tank is a 6x6-superpixel (12x12-pixel) sprite at superpixel
\ (player_sx, player_sy), the top-left of its footprint. Sprites are drawn
\ directly into screen memory, so they must never be mistaken for territory:
\ before a sprite is drawn, the screen bytes beneath it are saved, and before
\ the world is next updated every sprite is removed by restoring those bytes.
\
\ The draw cycle (see the design document):
\   hide_sprites   restore each player's saved background, in REVERSE player
\                  order, so that where sprites overlap, the earlier sprite's
\                  background (saved first, beneath the later sprite) is put
\                  back last and the bare arena reappears exactly
\   ... update the world on the bare arena ...
\   show_sprites   for each player in order: save the background, then draw
\
\ Screen footprint: a sprite covers raster lines 2*sy .. 2*sy+11 and pixel
\ columns 2*sx .. 2*sx+11. For even sx it starts at the left of screen byte
\ column sx DIV 2; for odd sx, two pixels in. Either way four byte columns
\ are saved, restored and drawn (the unused column of an even-aligned frame
\ has an all-zero mask). Each 12-line block is walked as 6 superpixel rows of
\ 2 raster lines x 4 bytes = 8 bytes; sprite_line_offsets gives each byte's
\ offset from the row's top-line address, so one index register (X) walks
\ the frame, the save buffer and the offsets together, while Y holds the
\ screen offset for (zp_screen_ptr),Y.
\
\ Self-modifying code: the absolute addresses of the frame planes and of the
\ player's save buffer are patched into the loops' LDA/STA abs,X operands
\ before each loop runs (marked PATCHED). That keeps the inner loops to
\ abs,X and (zp),Y accesses with no extra pointer arithmetic.
\
\ Colour: frames hold a mask plane (ones where opaque) and a select plane
\ (ones where the player's ink shows, else the contrast ink). The colour of
\ a byte is  contrast EOR ((contrast EOR ink) AND select),  merged into the
\ screen with  screen EOR ((screen EOR colour) AND mask).
\
\ Requires: zeropage.asm, screen_tables.asm, sprite_data.asm, level_data.asm,
\ and the player state and sprite_save_buffers defined by the program.
\ ============================================================================

MAX_PLAYERS = 4

\ ----------------------------------------------------------------------------
\ place_players -- set up the players for level zp_level
\
\ On exit:  player_count and each player's position, facing and ink set from
\           the level's level_players record; control sources set (player 1
\           keyboard layout A, player 2 layout B, the rest none); inputs,
\           accumulators and the tick count cleared; no sprites shown
\           A, X, Y corrupted
\ ----------------------------------------------------------------------------

.place_players
    \ X = zp_level * LEVEL_PLAYERS_RECORD (17 = 16 + 1).
    LDA zp_level
    ASL A
    ASL A
    ASL A
    ASL A
    CLC
    ADC zp_level
    TAX

    LDA level_players,X        \ Number of players (2 or 4).
    STA player_count

    LDY #0                     \ Y = player slot; X walks the record.
.place_players_loop
    LDA level_players+1,X
    STA player_sx,Y
    LDA level_players+2,X
    STA player_sy,Y
    LDA level_players+3,X
    STA player_facing,Y
    LDA level_players+4,X
    STA player_ink,Y
    LDA default_controls,Y     \ Keyboard for the first two players.
    STA player_control,Y
    LDA #NO_DIRECTION
    STA player_input,Y
    LDA #0
    STA player_accumulator,Y
    INX                        \ Next four-byte slot record.
    INX
    INX
    INX
    INY
    CPY #MAX_PLAYERS
    BNE place_players_loop

    LDA #0                     \ Nothing is on screen to restore yet.
    STA sprites_shown
    STA tick_count
    STA tick_count+1
    RTS

.default_controls
    EQUB CONTROL_KEYS_A, CONTROL_KEYS_B, CONTROL_NONE, CONTROL_NONE

\ ----------------------------------------------------------------------------
\ show_sprites -- save the background under, then draw, each player in order
\ hide_sprites -- restore every player's background in reverse order
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.show_sprites
    LDX #0
.show_sprites_loop
    CPX player_count
    BEQ show_sprites_done
    STX zp_player
    JSR save_under
    LDX zp_player
    JSR draw_sprite
    LDX zp_player
    INX
    JMP show_sprites_loop
.show_sprites_done
    LDA #1
    STA sprites_shown
    RTS

.hide_sprites
    LDA sprites_shown          \ Nothing to do if no sprites are on screen.
    BEQ hide_sprites_done
    LDX player_count           \ X counts down from player_count - 1 to 0.
.hide_sprites_loop
    DEX
    BMI hide_sprites_hidden    \ Stop once X wraps below 0.
    STX zp_player
    JSR restore_under
    LDX zp_player
    JMP hide_sprites_loop
.hide_sprites_hidden
    LDA #0
    STA sprites_shown
.hide_sprites_done
    RTS

\ ----------------------------------------------------------------------------
\ locate_sprite -- prepare to walk a sprite's screen footprint
\
\ On entry:  A = sx, Y = sy of the footprint's top-left superpixel
\ On exit:   zp_sprite_column = (sx DIV 2) * 8, the offset of its first byte
\            column; zp_sprite_row_sy = sy
\            A corrupted
\ ----------------------------------------------------------------------------

.locate_sprite
    STY zp_sprite_row_sy
    AND #&FE                   \ (sx AND &FE) * 4 = (sx DIV 2) * 8, up to
    ASL A                      \ 488, so the second ASL may carry into a
    ASL A                      \ ninth bit, which ROL moves into the high
    STA zp_sprite_column       \ byte.
    LDA #0
    ROL A
    STA zp_sprite_column+1
    RTS

\ ----------------------------------------------------------------------------
\ sprite_row_pointer -- point zp_screen_ptr at the next superpixel row
\
\ On entry:  zp_sprite_row_sy = the superpixel row; zp_sprite_column set
\ On exit:   zp_screen_ptr = address of that row's top raster line in the
\            sprite's first byte column; zp_sprite_row_sy advanced by one
\            A, Y corrupted; X preserved
\ ----------------------------------------------------------------------------

.sprite_row_pointer
    LDY zp_sprite_row_sy
    CLC
    LDA superpixel_row_lo,Y
    ADC zp_sprite_column
    STA zp_screen_ptr
    LDA superpixel_row_hi,Y
    ADC zp_sprite_column+1
    STA zp_screen_ptr+1
    INC zp_sprite_row_sy
    RTS

\ ----------------------------------------------------------------------------
\ point_at_save_buffer -- patch a loop operand to player X's save buffer
\
\ On entry:  X = player
\ On exit:   A = low byte, zp_sprite_tmp = high byte of
\            sprite_save_buffers + X * SPRITE_FRAME_BYTES (48)
\ ----------------------------------------------------------------------------

.point_at_save_buffer
    TXA                        \ X * 48 = X * 32 + X * 16 (at most 144).
    ASL A
    ASL A
    ASL A
    ASL A
    STA zp_sprite_tmp          \ X * 16
    ASL A                      \ X * 32
    CLC
    ADC zp_sprite_tmp
    CLC
    ADC #LO(sprite_save_buffers)
    PHA
    LDA #HI(sprite_save_buffers)
    ADC #0                     \ Carry from the low byte.
    STA zp_sprite_tmp
    PLA
    RTS

\ ----------------------------------------------------------------------------
\ save_under -- save the screen bytes under player X's sprite
\
\ On entry:  X = player
\ On exit:   the 48 bytes saved in the player's buffer; saved_sx/saved_sy
\            record where they came from; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.save_under
    JSR point_at_save_buffer
    STA save_under_store+1     \ PATCHED: STA buffer,X below.
    LDA zp_sprite_tmp
    STA save_under_store+2

    LDA player_sx,X            \ Remember where this background came from,
    STA saved_sx,X             \ for restore_under.
    LDY player_sy,X
    TYA
    STA saved_sy,X
    LDA player_sx,X
    JSR locate_sprite

    LDX #0                     \ X = frame byte 0..47.
.save_under_row
    JSR sprite_row_pointer
.save_under_byte
    LDY sprite_line_offsets,X
    LDA (zp_screen_ptr),Y
.save_under_store
    STA &FFFF,X                \ PATCHED to the player's save buffer.
    INX
    TXA
    AND #7                     \ Eight bytes per superpixel row.
    BNE save_under_byte
    CPX #SPRITE_FRAME_BYTES
    BNE save_under_row
    RTS

\ ----------------------------------------------------------------------------
\ restore_under -- put back the screen bytes saved under player X's sprite
\
\ On entry:  X = player (whose background was saved by save_under)
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.restore_under
    JSR point_at_save_buffer
    STA restore_under_load+1   \ PATCHED: LDA buffer,X below.
    LDA zp_sprite_tmp
    STA restore_under_load+2

    LDY saved_sy,X             \ Restore where the background was saved,
    LDA saved_sx,X             \ wherever the player has moved to since.
    JSR locate_sprite

    LDX #0
.restore_under_row
    JSR sprite_row_pointer
.restore_under_byte
    LDY sprite_line_offsets,X
.restore_under_load
    LDA &FFFF,X                \ PATCHED to the player's save buffer.
    STA (zp_screen_ptr),Y
    INX
    TXA
    AND #7
    BNE restore_under_byte
    CPX #SPRITE_FRAME_BYTES
    BNE restore_under_row
    RTS

\ ----------------------------------------------------------------------------
\ draw_sprite -- draw player X's tank at its position and facing
\
\ On entry:  X = player
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.draw_sprite
    \ Colours: zp_sprite_contrast = contrast ink byte; zp_sprite_xor =
    \ contrast EOR player ink, so contrast EOR (xor AND select) picks the
    \ player's ink where select is set.
    LDY player_ink,X
    LDA contrast_ink_bytes,Y
    STA zp_sprite_contrast
    EOR ink_bytes,Y
    STA zp_sprite_xor

    \ Frame = facing * 2 + (sx AND 1); patch its planes into the loop.
    LDA player_sx,X
    AND #1
    STA zp_sprite_tmp
    LDA player_facing,X
    ASL A
    ORA zp_sprite_tmp
    TAY
    LDA sprite_select_lo,Y
    STA draw_sprite_select+1   \ PATCHED: LDA select,X below.
    LDA sprite_select_hi,Y
    STA draw_sprite_select+2
    LDA sprite_mask_lo,Y
    STA draw_sprite_mask+1     \ PATCHED: AND mask,X below.
    LDA sprite_mask_hi,Y
    STA draw_sprite_mask+2

    LDY player_sy,X
    LDA player_sx,X
    JSR locate_sprite

    LDX #0
.draw_sprite_row
    JSR sprite_row_pointer
.draw_sprite_byte
    LDY sprite_line_offsets,X
.draw_sprite_select
    LDA &FFFF,X                \ PATCHED: select plane.
    AND zp_sprite_xor          \ Colour byte: player ink where selected,
    EOR zp_sprite_contrast     \ contrast ink elsewhere.
    EOR (zp_screen_ptr),Y      \ Merge under the mask:
.draw_sprite_mask
    AND &FFFF,X                \ PATCHED: mask plane.
    EOR (zp_screen_ptr),Y      \ screen EOR ((screen EOR colour) AND mask).
    STA (zp_screen_ptr),Y
    INX
    TXA
    AND #7
    BNE draw_sprite_byte
    CPX #SPRITE_FRAME_BYTES
    BNE draw_sprite_row
    RTS
