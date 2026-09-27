\ ============================================================================
\ flow.asm -- player selection, sessions and demo mode
\
\ select_players  Level 1 is drawn as a backdrop and the HUD invites players
\                 to press fire within SELECT_SECONDS. Each of the set's
\                 player slots (C, M in a two-player set; C, M, Y, K in a
\                 four-player one) has its own keyboard layout (key_layouts),
\                 and its fire key joins it. How a player joins chooses its
\                 control (session_controls): today always the keyboard; a
\                 joystick's fire button will choose the joystick. Play
\                 starts when the time runs out, or as soon as every slot
\                 has joined. Every slot nobody joins is played by the
\                 computer.
\
\ The game plays only the level set the loader loaded: all two-player or
\ all four-player levels.
\
\ A session plays every level in turn (play_session_level). After each
\ round's reveal, after_round awards points by rank -- 3, 2, 1, 0 for first
\ to last with four players, 3 and 0 with two, tied players sharing the
\ better rank -- shows the running totals, pauses, and moves on. After the
\ last level the totals are shown as final, then it is back to player
\ selection.
\
\ Demo (attract) mode: if nobody joins, the computer plays every slot, in
\ shorter rounds, cycling through the levels for ever -- until any player
\ key (a direction or fire of any layout) is pressed, which returns to
\ player selection.
\
\ Must match tools/dontdither/game.py (round_points).
\
\ Requires: os.asm, zeropage.asm, and the other game modules.
\ ============================================================================

SELECT_TEXT_ROW  = 6           \ "PRESS" "FIRE TO" "JOIN" below the title.
SELECT_COUNT_ROW = 10          \ The seconds left to join.
SELECT_SLOT_ROW  = 12          \ One row per player: "C CPU" or "C YOU".
POINTS_ROW       = 6           \ "POINTS"/"FINAL", then a row per player.
FIELDS_PER_SECOND = 50

\ ----------------------------------------------------------------------------
\ select_players -- let players join, then start a session. Never returns.
\ ----------------------------------------------------------------------------

.select_players
    LDX #&FF                   \ A fresh start: nothing below us on the
    TXS                        \ stack matters any more.

    LDA #0                     \ Level 1 as the backdrop.
    STA zp_level
    STA session_joined
    JSR draw_level
    SEND_VDU select_vdu_bytes, select_vdu_bytes_end

    LDX #0                     \ Everyone starts as the computer: a line for
.select_slots                  \ each of the set's players.
    STX zp_player
    JSR print_slot_status
    LDX zp_player
    INX
    CPX level_set_players
    BNE select_slots

    LDA #SELECT_SECONDS
    STA session_seconds
.select_second
    JSR print_select_count
    LDA #FIELDS_PER_SECOND
    STA session_fields
.select_field
    LDA #19                    \ Wait a field.
    JSR OSBYTE
    JSR next_random            \ Stir the generator: how long players take
                               \ to join varies it.
    LDX #0                     \ Each slot's fire key joins it.
.select_join_slot
    JSR layout_offset          \ A = the slot's layout (X preserved).
    JSR select_try_join
    LDX zp_player
    INX
    CPX level_set_players
    BNE select_join_slot
    LDA #21                    \ Discard the characters the keys typed.
    LDX #0
    JSR OSBYTE
    LDX level_set_players      \ Every slot has joined: start now. (The bit
    LDA player_bits,X          \ above the last slot's, less one, is all of
    SEC                        \ their bits.)
    SBC #1
    CMP session_joined
    BEQ select_start
    DEC session_fields
    BNE select_field
    DEC session_seconds
    BPL select_second          \ Down to and including 0.

.select_start
    \ Start the session. Nobody joined: demo mode, in shorter rounds.
    LDA session_joined
    STA session_humans
    LDA #LO(ROUND_TICKS)
    LDX #HI(ROUND_TICKS)
    LDY session_joined
    BNE select_round_length
    LDA #LO(DEMO_ROUND_TICKS)
    LDX #HI(DEMO_ROUND_TICKS)
.select_round_length
    STA round_length_ticks
    STX round_length_ticks+1
    LDA #0
    STA session_level
    LDX #MAX_PLAYERS - 1
.select_clear_points
    STA session_points,X
    DEX
    BPL select_clear_points
    \ Fall through.

\ ----------------------------------------------------------------------------
\ play_session_level -- play the session's current level. Never returns.
\ ----------------------------------------------------------------------------

.play_session_level
    LDA session_level
    STA zp_level
    JSR show_title_card
    JMP enter_level

\ ----------------------------------------------------------------------------
\ show_title_card -- announce level zp_level before it is played
\
\ The arena goes black (every cell solid K) and "LEVEL n" and the level's
\ title appear centred across it. After a pause the level is drawn over it.
\ ----------------------------------------------------------------------------

TITLE_CARD_ROW = 13            \ "LEVEL n"; the title two rows below.
ARENA_TEXT_COLUMNS = 32

.show_title_card
    JSR clear_hud
    LDX #STATE_ALL_K           \ A black arena.
    JSR fill_arena_with_state

    LDA #VDU_TEXT_COLOUR       \ "LEVEL n" in cyan, centred: "LEVEL " is 6
    JSR OSWRCH                 \ characters and n one or two, so start at
    LDA #1                     \ column 12 for 8 characters.
    JSR OSWRCH
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #(ARENA_TEXT_COLUMNS - 8) DIV 2
    JSR OSWRCH
    LDA #TITLE_CARD_ROW
    JSR OSWRCH
    JSR print_level_number

    LDA #VDU_TEXT_COLOUR       \ The title in yellow, centred.
    JSR OSWRCH
    LDA #3
    JSR OSWRCH
    JSR select_level           \ level_title: the level's title.
    LDA level_title
    STA zp_screen_ptr
    LDA level_title+1
    STA zp_screen_ptr+1
    LDY #0
    LDA (zp_screen_ptr),Y      \ Its length.
    STA session_fields         \ (borrowed)
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #ARENA_TEXT_COLUMNS    \ Column (32 - length) DIV 2.
    SEC
    SBC session_fields
    LSR A
    JSR OSWRCH
    LDA #TITLE_CARD_ROW + 2
    JSR OSWRCH
.show_title_card_char
    INY
    LDA (zp_screen_ptr),Y
    JSR OSWRCH
    CPY session_fields
    BNE show_title_card_char
.title_card_shown              \ Tests stop here.
    LDA #3
    JMP pause_seconds          \ Tail call; in demo mode a key may leave.

\ select_try_join: if the keyboard layout at offset A in key_layouts has
\ fire held, player X joins (if not already joined), on the keyboard, and
\ shows it.
.select_try_join
    STX zp_player
    JSR scan_layout            \ A = input byte.
    AND #FIRE_BIT
    BEQ select_try_join_done
    LDX zp_player
    LDA player_bits,X          \ This player's bit in session_joined.
    BIT session_joined
    BNE select_try_join_done   \ Already joined.
    ORA session_joined
    STA session_joined
    LDA #CONTROL_KEYS          \ Joined with a fire key: the keyboard.
    STA session_controls,X
    JSR print_slot_status
.select_try_join_done
    RTS

\ print_slot_status: "C CPU" or "C YOU" for player zp_player, in its colour.
.print_slot_status
    JSR set_text_colour
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #HUD_TEXT_COLUMN + 1
    JSR OSWRCH
    LDA zp_player
    CLC
    ADC #SELECT_SLOT_ROW
    JSR OSWRCH
    LDX zp_player
    LDA ink_letters,X
    JSR OSWRCH
    LDA #' '
    JSR OSWRCH
    LDX zp_player
    LDA player_bits,X
    AND session_joined
    BEQ print_slot_cpu
    SEND_VDU you_text, you_text_end
    RTS
.print_slot_cpu
    SEND_VDU cpu_text, cpu_text_end
    RTS

\ print_select_count: the seconds left, as two digits.
.print_select_count
    LDA #VDU_TEXT_COLOUR
    JSR OSWRCH
    LDA #3
    JSR OSWRCH
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #HUD_CLOCK_COLUMN + 1
    JSR OSWRCH
    LDA #SELECT_COUNT_ROW
    JSR OSWRCH
    LDA session_seconds
    JSR two_digits
    JSR OSWRCH
    TXA
    JMP OSWRCH

\ set_text_colour: MOS text colour for player zp_player's ink: its logical
\ colour, except black, shown in yellow (logical 3) so it is visible.
.set_text_colour
    LDA #VDU_TEXT_COLOUR
    JSR OSWRCH
    LDX zp_player
    LDA ink_text_colours,X
    JMP OSWRCH

\ ----------------------------------------------------------------------------
\ after_round -- award points, show totals, and go on. Never returns.
\ ----------------------------------------------------------------------------

.after_round
    \ Points by rank: rank = number of players with a strictly larger share.
    LDX #0
.after_round_player
    CPX player_count
    BEQ after_round_points_done
    LDY #0                     \ Y counts players ahead of player X.
    STY zp_ai_total            \ (borrowed: the counter)
.after_round_compare
    CPY player_count
    BEQ after_round_ranked
    LDA player_percent,Y
    CMP player_percent,X
    BEQ after_round_next_other
    BCC after_round_next_other
    INC zp_ai_total            \ Y's share is larger.
.after_round_next_other
    INY
    JMP after_round_compare
.after_round_ranked
    LDA zp_ai_total            \ Points: points_by_rank[4-player?0:4 + rank].
    LDY player_count
    CPY #MAX_PLAYERS
    BEQ after_round_four
    CLC
    ADC #4
.after_round_four
    TAY
    LDA points_by_rank,Y
    CLC
    ADC session_points,X
    STA session_points,X
    INX
    JMP after_round_player
.after_round_points_done
.points_awarded                \ Tests stop here to check the points.

    \ The next level, or the end of the session.
    INC session_level
    LDA session_level
    CMP level_set_count
    BCC after_round_show
    LDA session_humans         \ Demo mode cycles the levels for ever.
    BNE after_round_final
    LDA #0
    STA session_level
.after_round_show
    LDX #LO(points_text)
    LDY #HI(points_text)
    JSR show_totals
    LDA #5
    JSR pause_seconds
    JMP play_session_level

.after_round_final
    LDX #LO(final_text)
    LDY #HI(final_text)
    JSR show_totals
    LDA #10
    JSR pause_seconds
    JMP select_players

\ show_totals: a heading (6 characters at X, Y) and each player's total.
.show_totals
    STX zp_screen_ptr
    STY zp_screen_ptr+1
    LDA #VDU_TEXT_COLOUR
    JSR OSWRCH
    LDA #3
    JSR OSWRCH
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #HUD_TEXT_COLUMN + 1
    JSR OSWRCH
    LDA #POINTS_ROW
    JSR OSWRCH
    LDY #0
.show_totals_heading
    LDA (zp_screen_ptr),Y
    JSR OSWRCH
    INY
    CPY #6
    BNE show_totals_heading
    LDX #0
.show_totals_player
    STX zp_player
    JSR set_text_colour
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #HUD_TEXT_COLUMN + 1
    JSR OSWRCH
    LDA zp_player
    CLC
    ADC #POINTS_ROW + 1
    JSR OSWRCH
    LDX zp_player
    LDA ink_letters,X
    JSR OSWRCH
    LDA #' '
    JSR OSWRCH
    JSR OSWRCH
    LDX zp_player
    LDA session_points,X
    JSR two_digits
    CMP #'0'                   \ No leading zero.
    BNE show_totals_tens
    LDA #' '
.show_totals_tens
    JSR OSWRCH
    TXA
    JSR OSWRCH
    LDX zp_player
    INX
    CPX #MAX_PLAYERS
    BNE show_totals_player
    RTS

\ ----------------------------------------------------------------------------
\ pause_seconds -- wait A seconds; in demo mode, a player key returns to
\ player selection instead
\ ----------------------------------------------------------------------------

.pause_seconds
    STA session_seconds
.pause_second
    LDA #FIELDS_PER_SECOND
    STA session_fields
.pause_field
    LDA #19
    JSR OSBYTE
    JSR check_demo_exit
    DEC session_fields
    BNE pause_field
    DEC session_seconds
    BNE pause_second
    RTS

\ check_demo_exit: in demo mode (no humans), any player key -- a direction
\ or fire of either layout -- abandons the demo for player selection.
.check_demo_exit
    LDA session_humans
    BNE check_demo_exit_done
    LDX #MAX_PLAYERS - 1       \ Any key of any layout.
.check_demo_exit_layout
    STX zp_player
    JSR layout_offset
    JSR scan_layout
    CMP #NO_DIRECTION
    BNE check_demo_exit_yes
    LDX zp_player
    DEX
    BPL check_demo_exit_layout
.check_demo_exit_done
    RTS
.check_demo_exit_yes
    JMP select_players         \ Never returns; resets the stack.

\ ----------------------------------------------------------------------------
\ Data
\ ----------------------------------------------------------------------------

.player_bits                   \ Player X's bit in session_joined/_humans,
    EQUB &01, &02, &04, &08    \ and the bit above the last slot's (for a
    EQUB &10                   \ mask of every slot).

.points_by_rank
    EQUB 3, 2, 1, 0            \ Four players: first..last.
    EQUB 3, 0                  \ Two players.

.ink_letters
    EQUS "CMYK"
.ink_text_colours              \ Logical colour for each player's text:
    EQUB 1, 2, 3, 3            \ C, M, Y, and yellow for K.

.select_vdu_bytes
    EQUB VDU_TEXT_COLOUR, 3
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 1, SELECT_TEXT_ROW
    EQUS "PRESS"
    EQUB VDU_TAB, HUD_TEXT_COLUMN, SELECT_TEXT_ROW + 1
    EQUS "FIRE TO"
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 2, SELECT_TEXT_ROW + 2
    EQUS "JOIN"
.select_vdu_bytes_end

.cpu_text
    EQUS "CPU"
.cpu_text_end
.you_text
    EQUS "YOU"
.you_text_end
.points_text
    EQUS "POINTS"
.final_text
    EQUS "FINAL "
