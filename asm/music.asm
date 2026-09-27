\ ============================================================================
\ music.asm -- a 50 Hz music player driving the SN76489 directly
\
\ Plays a song (generated from tools/dontdither/splash_theme.py into
\ build/generated/splash_theme.asm) on the chip's four channels -- tone
\ channels 0-2 and the noise channel 3 -- once per vertical sync, from the
\ MOS's vsync event, so the rest of the program (and the MOS) carry on as
\ usual. It must match tools/dontdither/music.py's Player tick for tick:
\ the tests compare the chip's registers with it.
\
\ The song format (see music.py): each channel has a byte stream of
\   &00-&5F  a note (a semitone index; on the noise channel, the noise
\            control value 0-7) for the current duration
\   &60      a rest for the current duration
\   &80-&BF  set the duration to (b AND &3F) + 1 ticks
\   &C0-&DF  set the instrument to b AND &1F
\   &F0 l h  call the pattern at h*256+l;  &F1 return;  &FF back to the start
\ An instrument has an envelope (an attenuation per tick; bit 7 marks the
\ last, which is held) and an arpeggio (semitone offsets per tick, 7-bit
\ two's complement; bit 7 marks the last, after which it goes back to its
\ loop point).
\
\ Every tick, for each channel 0-3 in turn: count down the note; when it
\ runs out, read the stream up to the next note or rest (a note restarts
\ the envelope and arpeggio; on the noise channel it writes the noise
\ control register, which restarts the noise). Then write the tone period
\ (tone channels: the note's, moved by the arpeggio) and the attenuation
\ (the envelope's, or silent when resting).
\
\ Writing the chip (Advanced User Guide; MOS 1.20 .sendToSoundChip): the
\ byte goes out on System VIA port A (&FE4F, no handshake) with port A all
\ outputs (DDRA &FE43 = &FF), then the chip's write enable -- bit 0 of the
\ addressable latch, set through &FE40 -- is held low for at least 8 us.
\ The MOS keyboard scan, in its interrupt, uses port A as well (and sets
\ DDRA to &7F), so writes happen with interrupts off; here they are made
\ from the vsync event, which runs inside the MOS's interrupt handler.
\
\ Zero page: MUSIC_POINTER (2 bytes), used only inside the event, from
\ which the main program is excluded.
\
\ Entry points: music_start (from the start of the song) and music_stop
\ (silences the chip and unhooks the event).
\ ============================================================================

MUSIC_POINTER   = &72          \ In the MOS's user zero page (&70-&8F).
MUSIC_CHANNELS  = 4
MUSIC_NOISE     = 3
MUSIC_REST      = &60
MUSIC_SILENT    = 15

EVENTV          = &0220        \ The MOS event vector.
EVENT_VSYNC     = 4
SYSTEM_VIA_ORB  = &FE40        \ Port B: the addressable latch.
SYSTEM_VIA_DDRA = &FE43
SYSTEM_VIA_ORA_NH = &FE4F      \ Port A without handshake.
LATCH_SOUND_ON  = &00          \ Latch bit 0 low: the chip's write enable.
LATCH_SOUND_OFF = &08          \ Latch bit 0 high.

\ ----------------------------------------------------------------------------
\ music_start -- start the song from its beginning, 50 times a second
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.music_start
    LDX #MUSIC_CHANNELS - 1
.music_start_channel
    LDA music_stream_lo,X      \ Each channel at the start of its stream...
    STA music_pointer_lo,X
    LDA music_stream_hi,X
    STA music_pointer_hi,X
    LDA #1                     \ ...reading it on the first tick...
    STA music_wait,X
    STA music_duration,X
    LDA #0
    STA music_instrument,X
    LDA #MUSIC_REST            \ ...and silent until then.
    STA music_note,X
    DEX
    BPL music_start_channel

    SEI                        \ Hook the event vector, keeping the old one.
    LDA EVENTV
    STA music_old_eventv
    LDA EVENTV+1
    STA music_old_eventv+1
    LDA #LO(music_event)
    STA EVENTV
    LDA #HI(music_event)
    STA EVENTV+1
    CLI
    LDA #14                    \ *FX14,4: enable the vsync event.
    LDX #EVENT_VSYNC
    JMP OSBYTE                 \ Tail call.

\ ----------------------------------------------------------------------------
\ music_stop -- stop the song and silence the chip
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.music_stop
    LDA #13                    \ *FX13,4: disable the vsync event first, so
    LDX #EVENT_VSYNC           \ no tick sounds a note after the silence.
    JSR OSBYTE
    SEI
    LDA music_old_eventv       \ Unhook.
    STA EVENTV
    LDA music_old_eventv+1
    STA EVENTV+1
    LDX #MUSIC_CHANNELS - 1    \ Every channel silent: &9F, &BF, &DF, &FF.
.music_stop_channel
    TXA
    ASL A
    ASL A
    ASL A
    ASL A
    ASL A
    ORA #&90 OR MUSIC_SILENT
    JSR music_write
    DEX
    BPL music_stop_channel
    CLI
    RTS

\ ----------------------------------------------------------------------------
\ music_event -- the event handler: a tick on each vertical sync
\
\ Called by the MOS from its interrupt handler with the event number in A
\ and interrupts off; it restores A and the flags, but X and Y are ours to
\ keep. Other events go to the old handler.
\ ----------------------------------------------------------------------------

.music_event
    CMP #EVENT_VSYNC
    BEQ music_event_vsync
    JMP (music_old_eventv)
.music_event_vsync
    TXA
    PHA
    TYA
    PHA
    JSR music_tick
    PLA
    TAY
    PLA
    TAX
    LDA #EVENT_VSYNC
    RTS

\ ----------------------------------------------------------------------------
\ music_tick -- one tick of every channel (see the file header)
\ ----------------------------------------------------------------------------

.music_tick
    LDX #0
.music_tick_channel
    STX music_channel
    DEC music_wait,X           \ The note or rest runs out: read on.
    BNE music_tick_sound
    JSR music_advance
    LDX music_channel
.music_tick_sound
    LDA music_note,X
    CMP #MUSIC_REST
    BNE music_tick_note
    LDA #MUSIC_SILENT          \ Resting: silent.
    JMP music_tick_attenuation

.music_tick_note
    LDY music_instrument,X     \ The envelope: this tick's attenuation, then
    LDA music_envelope_lo,Y    \ on to the next unless this is the last.
    STA MUSIC_POINTER
    LDA music_envelope_hi,Y
    STA MUSIC_POINTER+1
    LDY music_envelope_step,X
    LDA (MUSIC_POINTER),Y
    BMI music_tick_envelope_held
    INC music_envelope_step,X
.music_tick_envelope_held
    AND #&0F
    STA music_attenuation

    CPX #MUSIC_NOISE           \ The noise channel has no tone period.
    BEQ music_tick_attenuation_saved

    LDY music_instrument,X     \ The arpeggio: this tick's offset, then on
    LDA music_arpeggio_lo,Y    \ to the next, or back to the loop point
    STA MUSIC_POINTER          \ after the last.
    LDA music_arpeggio_hi,Y
    STA MUSIC_POINTER+1
    LDY music_arpeggio_step,X
    LDA (MUSIC_POINTER),Y
    BMI music_tick_arpeggio_last
    INC music_arpeggio_step,X
    BPL music_tick_arpeggio_offset   \ (Always: steps are small.)
.music_tick_arpeggio_last
    PHA
    LDY music_instrument,X
    LDA music_arpeggio_loop,Y
    STA music_arpeggio_step,X
    PLA
.music_tick_arpeggio_offset
    AND #&7F                   \ 7-bit two's complement to 8-bit.
    CMP #&40
    BCC music_tick_arpeggio_positive
    ORA #&80
.music_tick_arpeggio_positive
    CLC
    ADC music_note,X           \ The sounding note (music_write corrupts Y,
    STA music_index            \ so it is kept).

    TXA                        \ Tone latch byte: %1 cc 0 pppp.
    ASL A
    ASL A
    ASL A
    ASL A
    ASL A
    ORA #&80
    STA music_latch
    LDY music_index
    LDA music_period_lo,Y
    AND #&0F
    ORA music_latch
    JSR music_write_safely
    LDY music_index
    LDA music_period_hi,Y      \ Data byte: the period's top 6 bits,
    STA music_latch            \ (high byte * 16) OR (low byte DIV 16).
    LDA music_period_lo,Y
    LSR A
    LSR A
    LSR A
    LSR A
    ASL music_latch
    ASL music_latch
    ASL music_latch
    ASL music_latch
    ORA music_latch
    JSR music_write_safely
    LDX music_channel

.music_tick_attenuation_saved
    LDA music_attenuation
.music_tick_attenuation
    STA music_attenuation      \ Attenuation latch byte: %1 cc 1 vvvv.
    TXA
    ASL A
    ASL A
    ASL A
    ASL A
    ASL A
    ORA #&90
    ORA music_attenuation
    JSR music_write_safely

    LDX music_channel
    INX
    CPX #MUSIC_CHANNELS
    BEQ music_tick_done
    JMP music_tick_channel
.music_tick_done               \ Tests stop here: every register written.
    RTS

\ ----------------------------------------------------------------------------
\ music_advance -- read channel X's stream up to its next note or rest
\
\ On entry:  X = channel (also in music_channel)
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.music_advance
    LDA music_pointer_lo,X
    STA MUSIC_POINTER
    LDA music_pointer_hi,X
    STA MUSIC_POINTER+1
.music_advance_byte
    LDY #0
    LDA (MUSIC_POINTER),Y
    JSR music_next_byte        \ (Moves the pointer on; A, X preserved.)
    CMP #&FF                   \ The end: back to the start.
    BNE music_advance_not_end
    LDA music_stream_lo,X
    STA MUSIC_POINTER
    LDA music_stream_hi,X
    STA MUSIC_POINTER+1
    JMP music_advance_byte
.music_advance_not_end
    CMP #&F0                   \ Call a pattern: remember where to return.
    BNE music_advance_not_call
    LDA (MUSIC_POINTER),Y      \ (Y = 0.) The pattern's address...
    PHA
    INY
    LDA (MUSIC_POINTER),Y
    PHA
    LDA MUSIC_POINTER          \ ...and the return address, after it.
    CLC
    ADC #2
    STA music_return_lo,X
    LDA MUSIC_POINTER+1
    ADC #0
    STA music_return_hi,X
    PLA
    STA MUSIC_POINTER+1
    PLA
    STA MUSIC_POINTER
    JMP music_advance_byte
.music_advance_not_call
    CMP #&F1                   \ Return.
    BNE music_advance_not_return
    LDA music_return_lo,X
    STA MUSIC_POINTER
    LDA music_return_hi,X
    STA MUSIC_POINTER+1
    JMP music_advance_byte
.music_advance_not_return
    CMP #&C0                   \ &C0-&DF: the instrument. (&E0-&EF unused.)
    BCC music_advance_not_instrument
    AND #&1F
    STA music_instrument,X
    JMP music_advance_byte
.music_advance_not_instrument
    CMP #&80                   \ &80-&BF: the duration.
    BCC music_advance_note
    AND #&3F
    STA music_duration,X
    INC music_duration,X
    JMP music_advance_byte

.music_advance_note
    STA music_note,X           \ A note or a rest, for the duration.
    LDA music_duration,X
    STA music_wait,X
    LDA MUSIC_POINTER          \ Keep the place.
    STA music_pointer_lo,X
    LDA MUSIC_POINTER+1
    STA music_pointer_hi,X
    LDA music_note,X
    CMP #MUSIC_REST
    BEQ music_advance_done
    LDA #0                     \ A note: its envelope and arpeggio restart...
    STA music_envelope_step,X
    STA music_arpeggio_step,X
    CPX #MUSIC_NOISE           \ ...and on the noise channel, its noise.
    BNE music_advance_done
    LDA music_note,X
    AND #7
    ORA #&E0
    JSR music_write_safely
.music_advance_done
    RTS

\ music_next_byte: MUSIC_POINTER += 1. A, X, Y preserved.
.music_next_byte
    INC MUSIC_POINTER
    BNE music_next_byte_done
    INC MUSIC_POINTER+1
.music_next_byte_done
    RTS

\ ----------------------------------------------------------------------------
\ music_write -- write byte A to the sound chip
\
\ On entry:  A = the byte; interrupts off (the MOS keyboard scan shares
\            port A)
\ On exit:   A, X preserved; Y corrupted
\ ----------------------------------------------------------------------------

.music_write_safely            \ (From the event: interrupts are already off.)
.music_write
    LDY #&FF                   \ Port A: all outputs.
    STY SYSTEM_VIA_DDRA
    STA SYSTEM_VIA_ORA_NH      \ The byte on the bus...
    LDY #LATCH_SOUND_ON        \ ...write enable low...
    STY SYSTEM_VIA_ORB
    LDY #2                     \ ...held at least 8 us (as the MOS does)...
.music_write_hold
    DEY
    BNE music_write_hold
    LDY #LATCH_SOUND_OFF       \ ...and high again.
    STY SYSTEM_VIA_ORB
    RTS

\ ----------------------------------------------------------------------------
\ Player state: per channel (X = 0-3), and working bytes
\ ----------------------------------------------------------------------------

.music_pointer_lo    SKIP MUSIC_CHANNELS   \ Where each channel reads next.
.music_pointer_hi    SKIP MUSIC_CHANNELS
.music_return_lo     SKIP MUSIC_CHANNELS   \ Where a pattern returns to.
.music_return_hi     SKIP MUSIC_CHANNELS
.music_wait          SKIP MUSIC_CHANNELS   \ Ticks until the next event.
.music_duration      SKIP MUSIC_CHANNELS   \ The current note length.
.music_instrument    SKIP MUSIC_CHANNELS
.music_note          SKIP MUSIC_CHANNELS   \ The note, or MUSIC_REST.
.music_envelope_step SKIP MUSIC_CHANNELS
.music_arpeggio_step SKIP MUSIC_CHANNELS
.music_channel       SKIP 1                \ The channel being ticked.
.music_attenuation   SKIP 1
.music_latch         SKIP 1                \ A latch byte being built.
.music_index         SKIP 1                \ The sounding note.
.music_old_eventv    SKIP 2
ASSERT LO(music_old_eventv) <> &FF   \ JMP (indirect) must not straddle a page.
