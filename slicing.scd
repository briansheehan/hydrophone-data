~riverBuf = Buffer.readChannel(s,PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/CATA01_051321-083106.flac", channels:[1]);

~riverBuf.play;

(
{
	var sig = PlayBuf.ar(1, ~riverBuf, BufRateScale.ir(~riverBuf));
	var slice_impulses = FluidOnsetSlice.ar(sig, metric:\rcomplex, threshold:0.5);
	sig = DelayN.ar(sig, maxdelaytime:1, delaytime:1024 * SampleDur.ir); // compensate for a latency of windowSize samples
	[sig, slice_impulses]
}.play;
)
