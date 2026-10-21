(
s.waitForBoot({
	// Create a buffer with the source audio in a buffer called "src"
	var src = Buffer.read(s,
		PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav");

	// Create two buffers, h and p for the harmonic and percussive outputs respectively
	var h = Buffer.new(s);
	var p = Buffer.new(s);
	// Create a new buffer that we will compose into so harmonic and percussive exist in a two-channel buffer, rather than two separate mono buffers.
	var result = Buffer.new(s);
	var synth;

	("Processing:" + src.path).postln;
	// Do the HPSS processing. Only process the first channel to simplify things when we process a stereo file.
	// We call the processBlocking method in order to do synchronous calls that will happen in a deterministic order.
	// Later on you will see the process method being used to do asynchronous calls between the language and server.
	FluidBufHPSS.processBlocking(s, source:src, harmonic:h, percussive:p, numChans:1, maskingMode:1);
	FluidBufCompose.processBlocking(s, source:h, destination:result, destStartChan:0);
	FluidBufCompose.processBlocking(s, source:p, destination:result, destStartChan:1);
	s.sync;
	("FINISHED Processing:" + src.path).postln;
	synth = h.play;
	//s.sync;
	//synth.free; src.free; h.free; p.free;
})
)

(
SynthDef(\hpssStack, {|buf, out=0, whichSource=0, maskingMode=1, harmFilterSize=17, percFilterSize=31, windowSize=64, whichWindow=0|
	var buf_sig, sig_out, windows, harm, perc, residual;
	buf_sig = PlayBuf.ar(1, buf, BufRateScale.kr(buf),loop:1);
	windows = List.new;
	for (10, 16) {|i|
		postln(2**i);
		windows.add(FluidHPSS.ar(buf_sig, harmFilterSize:17, percFilterSize:31, maskingMode:maskingMode, windowSize:2**i));
	};
	#harm, perc, residual = Select.ar(whichWindow, windows);
	sig_out = Select.ar(whichSource, FluidHPSS.ar(harm, harmFilterSize:17, percFilterSize:31, maskingMode:maskingMode, windowSize:2**14));
	Out.ar(out, sig_out.dup);
}).add;
)

(
SynthDef(\timeStretch, {|buf, out=0|
	var buf_sig, osc_sig, sines, residual;
	buf_sig = PlayBuf.ar(1, buf, BufRateScale.kr(buf),loop:1);
	# sines, residual = FluidSines.ar(in:buf_sig);
	Out.ar(out, [residual, residual]);

}).add;

SynthDef(\pitchTrackOld, {|buf, out=0, confThresh=0.2, algorithm=2, hopSize=(-1)|
	var buf_sig, osc_sig, pitch, conf, confThreshMet;
	buf_sig = PlayBuf.ar(1, buf, BufRateScale.kr(buf),loop:1);
	# pitch, conf = FluidPitch.kr(in:buf_sig, hopSize:hopSize, algorithm:algorithm);
	confThreshMet = conf >= confThresh;
	osc_sig = SinOsc.ar(freq:pitch) * conf * confThreshMet;
	Out.ar(out, [osc_sig, osc_sig]);
}).add;
)

(
s.waitForBoot({
	SynthDef(\hpss, {|buf, out=0, whichSource=0, maskingMode=1, harmFilterSize=17, percFilterSize=31, windowSize=64, whichWindow=0|
		var in, windows, window, sig_out;
		in = PlayBuf.ar(1, buf, BufRateScale.kr(buf),loop:1);
		windows = List.new;
		"HPSS".postln;
		for (10, 14) {|i|
			postln(2**i);
			windows.add(FluidHPSS.ar(in, harmFilterSize:61, percFilterSize:31, maskingMode:maskingMode, windowSize:2**i));
		};
		window = Select.ar(whichWindow, windows);
		sig_out = Select.ar(whichSource, [in] ++ window);
		Out.ar(out, sig_out.dup);
	}).add;

	SynthDef(\pitchTrack, {|in, out=0, confThresh=0.2, algorithm=2, hopSize=(-1)|
		var osc_sig, pitch, conf, confThreshMet;
		# pitch, conf = FluidPitch.kr(in:In.ar(in), hopSize:hopSize, algorithm:algorithm);
		confThreshMet = conf >= confThresh;
		osc_sig = SinOsc.ar(freq:pitch) * conf * confThreshMet;
		Out.ar(out, [osc_sig, osc_sig]);
	}).add;

	SynthDef(\recordFFT, { |srcBuf, fftBuf, fftSize=1024, hopSize=0.25, winType=0|
		var sig, chain, localBuf;

		sig = PlayBuf.ar(1, srcBuf, BufRateScale.kr(srcBuf), doneAction:2);
		localBuf = LocalBuf.new(fftSize);
		chain = FFT(localBuf, sig, hopSize, winType);
		chain = PV_RecordBuf(chain, fftBuf, run:1, hop:hopSize, wintype:winType);
		Out.ar(0, 0);
	}).add;

	SynthDef(\playFFT, { |out=0, fftBuf, fftSize=1024, winType=0|
		var sig, chain, localbuf;
		localbuf = LocalBuf.new(fftSize);
		chain = PV_PlayBuf(localbuf, fftBuf, \rate.kr(1), loop:1);
		sig = IFFT(chain, winType);
		Out.ar(out, sig.dup);
}).add
})
)

(
var src = Buffer.read(s, PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav", action:{|buf| ~hpssSynth = Synth(\hpss, [buf])});
)

(
var src = Buffer.read(s, PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav", action:{|buf| ~hpssSynth = Synth(\hpssStack, [buf])});
)

(
var src = Buffer.read(s, PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav", action:{|buf| ~pitchSynth = Synth(\pitchTrackOld, [buf])});
)

(
x = Routine({
	var srcBuf, fftBuf, fftSize, hopSize;
	fftSize = 1024;
	hopSize = 0.25;
	srcBuf =  Buffer.read(s, PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav");
	s.sync;
	fftBuf = Buffer.alloc(s, (srcBuf.numFrames/srcBuf.sampleRate).calcPVRecSize(fftSize, hopSize, srcBuf.sampleRate));
	s.sync;
	Synth(\recordFFT, [\srcBuf, srcBuf, \fftBuf, fftBuf]);
	s.sync;
	~fftPlayer = Synth(\playFFT, [\fftBuf, fftBuf]);
}).play
)

(
y = Routine({
	var srcBuf, fftBuf, fftSize, hopSize, fftPlayerBus;
	fftSize = 1024;
	hopSize = 0.25;
	fftPlayerBus = Bus.audio;
	srcBuf =  Buffer.read(s, PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs/M-CATA01_051321-130025.wav");
	s.sync;
	fftBuf = Buffer.alloc(s, (srcBuf.numFrames/srcBuf.sampleRate).calcPVRecSize(fftSize, hopSize, srcBuf.sampleRate));
	s.sync;
	Synth(\recordFFT, [\srcBuf, srcBuf, \fftBuf, fftBuf]);
	s.sync;
	~fftPlayer = Synth(\playFFT, [\out, fftPlayerBus, \fftBuf, fftBuf]);
	~pitchSynth = Synth.after(~fftPlayer, \pitchTrack, [\in, fftPlayerBus]);
}).play
)



~loop_bus = Bus.audio;

~fftPlayer.set(\rate, 100);
~pitchSynth.set(\confThresh, 0.5


~pitchSynth.set(\algorithm, 0);
~pitchSynth.set(\algorithm, 1);
~pitchSynth.set(\algorithm, 2);
~pitchSynth.set(\hopSize, 128);
~pitchSynth.set(\confThresh, 0.7);

~hpssSynth.set(\maskingMode, 0);
~hpssSynth.set(\maskingMode, 1);
~hpssSynth.set(\maskingMode, 2);

~hpssSynth.set(\whichSource, 0);
~hpssSynth.set(\whichSource, 1);
~hpssSynth.set(\whichSource, 2);
~hpssSynth.set(\whichSource, 3);

~hpssSynth.set(\whichWindow, 0);
~hpssSynth.set(\whichWindow, 1);
~hpssSynth.set(\whichWindow, 2);
~hpssSynth.set(\whichWindow, 3);
~hpssSynth.set(\whichWindow, 4);
~hpssSynth.set(\whichWindow, 5);
~hpssSynth.set(\whichWindow, 6);
~hpssSynth.set(\whichWindow, 7);
~hpssSynth.set(\whichWindow, 8);
~hpssSynth.set(\whichWindow, 9);
~hpssSynth.set(\whichWindow, 10);

~pitchSynth.set(\confThresh, 0.5);