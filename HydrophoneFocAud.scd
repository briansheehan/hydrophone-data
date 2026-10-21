/*
One parameter, delta_f , controls the magnitude of a frequency shift. The second, c, sets the excursion of a pitch modulation.

The frequency shift delta_f is a free parameter of the method, which helps to yield a perceptually optimal frequency range of the sonification, e.g., somewhere within the range of 100 Hz and 2 kHz. If delta_f = 0, there is no difference to a pure audification.

The freely choosable parameter c controls the magnitude of the modulation:  Setting c = 0 results in a constant instantaneous frequency of the frequency modulation (FM) which is then independent of the data values x(t). This results in a pure frequency shift as described in Sect. 3.1.  Setting c = 1 leads to a transposition of one octave higher and lower for signal values x(t) = ± 1. The value of c has to be carefully chosen depending on the signal amplitude and bandwidth to prevent aliasing resulting from strong FM sidebands.

The implementation of Focused Audificaiton is simple and preserves preferable properties of audification whilst permitting a true “zooming” at any time scale for the interactive exploration of a data set.

One issue of FA when dealing with signals of harmonic complexes needs to be discussed. Many physical processes are—at least approximately—periodic. The related signals therefore consist of harmonic partials, and their audification makes use of human audition which groups these frequency components into a single auditory gestalt. In pure audification, frequency ratios and thus the periodicity of harmonic complexes are preserved, resulting in one “sound” with a certain timbre and pitch. In FA on the contrary, the frequency shift destroys the harmonic relationship between the partials and thus the periodicity of the signal. This results in a complex superposition of individual sinusoidal tracks instead of one gestalt with a certain timbre.
*/
(
~loop_bus = Bus.audio;
~lpf_bus = Bus.audio;
~currentDir = PathName(thisProcess.nowExecutingPath).parentPath;
~buffer1 = Buffer.read(s, ~currentDir ++ "seven-hours-ish.wav");

//not currently using this, it is used to allow a SuperCollider Collection to be normalised and loaded into a Buffer.
~loadfocusedaudification = {
    arg data, printtrue=0, normalizationlevel=1, datamin, datamax;
    var normdata;
    if(normalizationlevel==1, {normdata = data.normalize},
        {normdata = (data+datamin)/(datamax+datamin)}
    );

    if(printtrue==1, {normdata.plot}, {"no plot requested".postln});

//    ~mybuffer = Buffer.loadCollection(s, normdata, 1,  {"buffer ready".inform});
	Buffer.loadCollection(s, normdata, 1,  {"buffer ready".inform});
};

~mk_sldr = {|param, spec, target|
	Slider()
	.value_(spec.unmap(spec.default).postln)
	.action_({|self| target.set(param, spec.map(self.value).postln)})
	.fixedSize_(Size(20, 160))
};

~mk_sldr_col = {|text, param, spec, target|
	[StaticText().string_(text), ~mk_sldr.value(param, spec, target)]
};

SynthDef(\looper, {|out, buffer, rate|
	Out.ar(out, PlayBuf.ar(1, buffer, rate: BufRateScale.kr(buffer) * rate, loop: 1))
}).add;

//Low pass filter with bypass
SynthDef(\lpf, {|in, out, cutoff=10, lpf_on=0|
	var sig;
	sig = In.ar(in);
	sig = Select.ar(lpf_on, [sig, LPF.ar(sig, freq:cutoff)]);
	Out.ar(out, sig);
}).add;

SynthDef(\faud, {|in, out=0, c=0.25, deltaf=0, amp=0.5|
	var fMod, sin, cos, hilb, sig;

	sig = In.ar(in);
	fMod = (deltaf * (2 ** (sig * c)));
	//fMod.poll(10);
	sin = SinOsc.ar(fMod);
	cos = SinOsc.ar(fMod, 0.5pi);
	hilb = HilbertFIR.ar(sig, LocalBuf(4096)) * [cos, sin];
	//Out.ar(0, (hilb[0] - hilb[1]) * amp ! 2);
	Out.ar(out, LPF.ar(HPF.ar((hilb[0] - hilb[1]) * amp, 50), 20000) ! 2);
}).add;

//Original code from Katharina Groß-Vogt, Matthias Frank, and Robert Höldrich. “Focused Audification and the Optimization of Its Parameters.” Journal on Multimodal User Interfaces 14, no. 2 (2020): 187–98. https://doi.org/10.1007/s12193-019-00317-8. (Provided by Katharina Groß-Vogt)
SynthDef(\faud_orig, {
	|rate=0.05, c=0.25, deltaf=0, b=0, startpos=0, amp=0.5, lpf=10, lpf_on=0|
	var fMod, sin, cos, hilb, sig;

	sig = PlayBuf.ar(
		1, b, rate: BufRateScale.kr(b) * rate,
		startPos:startpos, loop: 1);
	//Added low pass filter to allow focused audification of infrafaud only.
	sig = Select.ar(lpf_on, [sig, LPF.ar(sig, freq:lpf)]);
	Out.ar(4, sig);
	fMod = (deltaf * (2 ** (sig * c)));
	//fMod.poll(10);
	sin = SinOsc.ar(fMod);
	cos = SinOsc.ar(fMod, 0.5pi);
	hilb = HilbertFIR.ar(sig, LocalBuf(4096)) * [cos, sin];
	//        Out.ar(0, (hilb[0] - hilb[1]) * amp ! 2);
	Out.ar(0, LPF.ar(HPF.ar((hilb[0] - hilb[1]) * amp, 50), 20000) ! 2);
}).add;
)

(
var r_spec, c_spec, df_spec, a_spec, lpf_spec;
var lpf_chckbx, lpf_on_col, r_col, c_col, df_col, lpf_col, amp_col;
var looper, lpf, faud;

//ControlSpecs for Focused Audification parameters.
r_spec = ControlSpec(0, 1000, default:1); //Playback rate of source audio
c_spec = ControlSpec(0, 100, default:0);//Scaling factor for 'excursion of frequency', seems to work like index of modulation in FM/AM
df_spec = ControlSpec(-1000, 2000.0, warp:\lin, default: 400, units:"Hz"); //Delta frequency: amount of frequency shift (positive)
a_spec = ControlSpec(0.001, 1, warp:\exp, default:0.5);//Amplitude control for output
lpf_spec = ControlSpec(0.25, 20000, warp:\exp, default:10, units:"Hz"); //Centre frequency of LP filter to preprocess infrasonic signals

looper = Synth.new(\looper, [out:~loop_bus, buffer:~buffer1, rate:r_spec.default]);
lpf = Synth.after(looper, \lpf, [in:~loop_bus, out:~lpf_bus, cutoff:lpf_spec.default, on:0 ]);
faud = Synth.after(lpf, \faud,
	[in:~lpf_bus, c:c_spec.default, deltaf:df_spec.default, amp:a_spec.default]);

w = Window("Focused audification");

/*m = PopUpMenu(w, Rect(50, 50, 200, 25));

// Define the menu options
m.items = ["Option A", "Option B", "Option C"];

// Define what happens when an item is selected
m.action = { |menu|
("Selected item index:" + menu.value).postln;
("Selected item name:" + menu.item).postln;
};*/

r_col = ~mk_sldr_col.value("Playback Rate", \rate, r_spec, looper);
lpf_chckbx = CheckBox(text:"LPF On").action_({|self| lpf.set(\lpf_on, self.value.binaryValue)});
lpf_on_col = [nil, lpf_chckbx];
lpf_col = ~mk_sldr_col.value("Low Pass Cutoff", \cutoff, lpf_spec, lpf);
df_col = ~mk_sldr_col.value("Frequency Shift", \deltaf, df_spec, faud);
c_col = ~mk_sldr_col.value("Frequency Excursion", \c, c_spec, faud);
amp_col = ~mk_sldr_col.value("Amplitude", \amp, a_spec, faud);

w.layout = GridLayout.columns(r_col, lpf_on_col, lpf_col, df_col, c_col, amp_col);
(r_col ++ lpf_col ++ df_col ++ c_col ++ amp_col).do({
	|item| w.layout.setAlignment(item, \center)
});

w.front;
w.onClose= {[faud, lpf, looper].do({|item| item.free})};
)