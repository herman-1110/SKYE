**Title:** RTSP/H264: no frames are ever emitted when the camera puts the RTP marker bit on a trailing SEI (TP-Link VIGI InSight S445)

**go2rtc version:** 1.9.14 (b5948cf), windows/amd64. `pkg/h264/rtp.go` on `master` has the same logic.

**Camera:** TP-Link VIGI InSight S445 v1.0, firmware 3.3.2 Build 260708. RTSP over TCP (interleaved). Captured on the sub stream (`/stream2`, H.264 High@3.0, 848x480, 25 fps).

### Symptom
- **WebRTC:** ICE and DTLS connect within half a second, but the browser never receives an RTP packet. No `inbound-rtp` stats appear, and the candidate pair carries only STUN keep-alives.
- **MP4:** `/api/stream.mp4` returns no bytes before timing out.
- **`/api/streams`:** the RTSP producer is receiving data. In about 8 s the receiver showed 766 packets and ~518 KB, and the MP4 consumer's sender counted the same bytes arriving. So packets reach the consumer, but nothing comes out of the H.264 depacketizer (see Cause).

### What the camera sends
From a raw capture of the RTSP/TCP interleaved channel, 8 s, 744 RTP packets, 200 frames:
- **Frame starts:** each IDR frame begins `SPS`, `PPS` (single-NAL packets, marker 0), then `FU-A[IDR]` fragments (marker 0). IDRs arrive every 2.0 s, starting with the first frame after PLAY.
- **Other frames:** P-frames are single-NAL slices or FU-A fragments, marker 0.
- **Frame ends:** every frame ends with a single-NAL **SEI** (type 6), 61-97 bytes, **with the marker bit set**.
  - All 200 marked packets in the capture are these SEIs.
  - Each is the last packet before the RTP timestamp changes.
  - No slice or FU-A end packet ever carries the marker.

The camera's SDP (stream2, abridged):
```
s=Session streamed by "TP-LINK RTSP Server"
a=smart_encoder:virtualIFrame=1
m=video 0 RTP/AVP 96
a=rtpmap:96 H264/90000
a=fmtp:96 packetization-mode=1; profile-level-id=64001E; sprop-parameter-sets=Z2QAHqwVFKDUPabgwMDIAAAfQAAGGoAg,aO48sA==
m=audio 0 RTP/AVP 8
a=rtpmap:8 PCMA/8000
```

### Cause
`pkg/h264/rtp.go`, in `RTPDepay`:
```go
if packet.Marker && len(payload) < PSMaxSize {
    switch NALUType(payload) {
    case NALUTypeSPS, NALUTypePPS:
        buf = append(buf, payload...)
        return
    case NALUTypeSEI:
        // RtspServer https://github.com/AlexxIT/go2rtc/issues/244
        // sends, marked SPS, marked PPS, marked SEI, marked IFrame
        return
    }
}
```
1. This camera's frame-ending SEI is marked and smaller than `PSMaxSize` (128), so it is dropped by `return`.
2. That `return` happens without flushing `buf`, which by then holds the whole access unit (the slices collected while `!packet.Marker`).
3. No other packet carries the marker, so `buf` is never emitted. It only grows until the 5 MB overflow guard resets it.
4. As a result nothing ever reaches `RTPPay` or the MP4 muxer.

### Possible fix
When a marked SEI arrives and `buf` already holds a slice (IDR or non-IDR), emit `buf` as the access unit, with or without the SEI, instead of returning.

Keep the current "drop it" behaviour only when `buf` holds no slice yet. That's the #244 RtspServer case, where the marked SEI comes before the I-frame.

A more general option: RFC 6184 §5.1 lets a receiver use the marker bit as an early hint that an access unit has ended, but not depend on it. Flushing `buf` when the RTP timestamp changes and `buf` already holds a slice would cover this camera and any other that mis-marks. It shouldn't change anything for cameras that mark correctly, because their `buf` is already empty when the timestamp changes.

### Workaround
An `exec:` source that pipes MPEG-TS bypasses the RTP depacketizer. Copying the video also lets ffmpeg strip the SEI:
```
exec:ffmpeg -loglevel quiet -rtsp_transport tcp -i rtsp://user:pass@camera/stream2 -map 0:v:0 -c:v copy -bsf:v filter_units=remove_types=6 -an -f mpegts -
```

The SDP advertises `smart_encoder:virtualIFrame=1`. Frigate's docs recommend turning Smart Coding off on VIGI cameras, but this model's web UI has no such setting, so I couldn't test whether the trailing SEI comes from it.
