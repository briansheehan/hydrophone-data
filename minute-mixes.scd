(
s.waitForBoot({
	~to_secs = Dictionary.newFrom([minute: 60, hour: 60*60, day: 24*60*60, week:7*24*60*60,
		fortnight:14*24*60*60, year: 365*24*60*60]);
	~rate = 20;
	~amp_scaling = 6;
	~metadata_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/output_metadata.csv";
	~audio_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/";

	~read_datetimes = { |filepath|
		var datetimes = CSVFileReader.read((filepath).resolveRelative,
			skipEmptyLines:true, skipBlanks:true);
		var col_names = datetimes.removeAt(0); //column headings.
		col_names = col_names.collect({|item, idx|
			if (item == "seconds_to_next") {
				\dur;
			} {
			item.asSymbol;
			}
		});
		datetimes = datetimes.collect({|row, idx|
			[row[0].asInteger, row[1].asInteger, row[2].asInteger, row[3].asInteger,
				row[4].asInteger, row[5].asInteger, row[6].asInteger, row[7].asInteger,
				row[8].asInteger, row[9], row[10], row[11]]
		});
		[col_names, datetimes];
	};

	~read_sunrises = { |filepath|
		var sunrises = CSVFileReader.read((filepath).resolveRelative,
			skipEmptyLines:true, skipBlanks:true);
		var col_names = sunrises.removeAt(0); //column headings.
		col_names = col_names.collect({|item, idx|
			if (item == "seconds_to_next") {
				\dur;
			} {
			item.asSymbol;
			}
		});
		sunrises = sunrises.collect({|row, idx|
			[row[0], row[1].asInteger, row[2].asInteger, row[3].asInteger, row[4].asInteger]
		});
		[col_names, sunrises];
	};


	~read_metadata = { |path|
		CSVFileReader.read(~metadata_path, skipEmptyLines:true, skipBlanks:true);
	};

	SynthDef(\sineSynth, { |freq=440, amp=1, kr_in=0, out=0|
		var osc, amp_env;
		amp_env = In.kr(kr_in);
		osc = SinOsc.ar(freq) * amp * amp_env;
		Out.ar(out, osc.dup);
	}).add;

	SynthDef(\playBufEnv, { |out=0, kr_out=0, buf, rate=1, attackTime=0.7, releaseTime=0.7|
		var sig, amp;
		#l,r = PlayBuf.ar(2, buf, rate:BufRateScale.ir(buf)*rate, doneAction: Done.freeSelf);
		amp = Amplitude.kr(r, attackTime:attackTime, releaseTime:releaseTime);
		Out.kr(kr_out, amp);
		Out.ar(out, r.dup);
	}).add;

	SynthDef(\daySon, { |out=0, amp=0.4, day_of_week, timeScale|
		var osc, env, sig;
		osc = SinOsc.ar((40 + day_of_week).midicps);
		env = EnvGen.kr(
			Env.linen(attackTime:~to_secs[\day]*0.01, sustainTime:~to_secs[\day]*0.98, releaseTime:~to_secs[\day]*0.01),
			timeScale: timeScale,
			doneAction: Done.freeSelf);
		sig = osc * env;
		Out.ar(out, sig.dup);
	}).add;

	SynthDef(\sunSon, { |out=0, freq=440, amp=0.4, timeScale, daylight, seconds_to_noon|
		var sig, env;
		// Envelope times are written in realtime seconds, before timeScale adjustment
		env = EnvGen.kr(
			Env.linen(attackTime:daylight*0.01, sustainTime:daylight*0.98, releaseTime:daylight*0.01),
			timeScale: timeScale,
			doneAction: Done.freeSelf
		);
		sig = SinOsc.ar(freq) * env * amp;

		Out.ar(out, [sig, sig]);
	}).add;

	SynthDef(\sampleSon, { |out=0, freq=440, amp=0.5, timeScale, sampleLength|
		var sig, env, env2;
		// Envelope times are written in realtime seconds, before timeScale adjustment
		env = EnvGen.kr(
			Env.perc(0.1*sampleLength, 0.9*sampleLength),
			timeScale: timeScale,
			doneAction: Done.freeSelf
		);
		sig = SinOsc.ar(freq) * env * amp;
		Out.ar(out, sig.dup);
	}).add;


	~minute_mixes = Routine({
		var metadata_2D_array = ~read_metadata.(~metadata_path);
		var metadata = List.new;

		metadata_2D_array.do {|array|
			metadata.add(List.newUsing(array))
		};


		metadata.removeAt(0); //Don't need column headings.
		metadata.do { |md_row|
			b = Buffer.read(s, ~audio_path ++ md_row[0]);
			md_row.add(b);

		};
		s.sync; //Wait for buffers to load

		metadata.do({ |md_row|
			var buf = md_row[md_row.size-1];
			var name = md_row[0];
			var num_wavs = md_row[1].asInteger;
			var lufs_i = md_row[4].asFloat;
			var amp = 10.pow(lufs_i/(20*~amp_scaling));
			var proportion_of_total = md_row[6].asFloat;
			a = Synth(\playBufEnv, [\buf, buf, \rate, ~rate]);
			b = Synth.after(a, \sineSynth, [\freq, num_wavs/5, \amp, amp]);
			((proportion_of_total*buf.duration)/~rate).wait; // Wait until the current buffer finishes
			a.free;
			b.free;
		});

		postln("Start freeing buffers");
		metadata.do {|md_row|
			var buf = md_row[md_row.size -1];
			buf.postln;
			free(buf);
		};
		postln("End freeing buffers");
	});
/*
	Excercise to explore using patterns. Build patterns to represent the data
	collection schedule of the river study:
	The daily pattern (every 15 mins for one minute)
	Every day during the study duration for that year.
	*/
	~makeDaysBind = { |filepath|
		var keys, days, firstJan, daysSeq, daysBind;

		#keys, days = ~read_datetimes.(filepath);
		keys.postln;
		firstJan = days[0][6].postln;//New Year's Day in raw seconds
		postln("Everydays size: " + days.size);
		daysSeq = Pseq(days);
		daysBind = Pbind(
			\instrument, \daySon,
			\timeScale, Pfunc({ thisThread.clock.beatDur }),
			\dur, ~to_secs[\day],
			keys, daysSeq
		);
		[firstJan, daysBind];
	};

	~makeSamplesBind = {|filepath, firstJan|
		var keys, samples, samplesSeq, daysSeq, secsToFirstSample, restToFirstSample, samplesBind;
		#keys, samples = ~read_datetimes.(filepath);
		keys.postln;
		postln("Datetimes size: " + samples.size);
		secsToFirstSample = samples[0][6] - firstJan; //samples[0][6] indexes the raw_seconds field of the first sample row
		restToFirstSample = [0,0,0,0,0,0,0, Rest(secsToFirstSample), 0, "None", "None", "None"]; // \dur key will map to the rest
		postf("Samples[0] size: %. restToFirstSample size: %\n", samples[0].size, restToFirstSample.size);
		restToFirstSample.postln;
		samplesSeq = Pseq([restToFirstSample] ++ samples);
		samples[0].postln;

		samplesBind = Pbind(
			\instrument, \sampleSon,
			\sampleLength, 60, //each sample is a wav 60 seconds long
			\timeScale, Pfunc({ thisThread.clock.beatDur }),
			keys, samplesSeq;
		);
	};

	~makeSunrisesBind = {|filepath, firstJan|
		var keys, sunrises, secsToFirstSunrise, restToFirstSunrise, sunrisesSeq, sunrisesBind;
		#keys, sunrises = ~read_sunrises.("McCoy_sunrise_sunset_2022.csv");
sunrises.postln;
keys.postln;
		secsToFirstSunrise = sunrises[0][1] - firstJan;
		restToFirstSunrise = ["None", 0, 0, 0, Rest(secsToFirstSunrise)]; // rest will map to the \dur key
		a = [restToFirstSunrise] ++ sunrises;
		a.postln;
		sunrisesSeq = Pseq(a);
		sunrisesBind = Pbind(
			\instrument, \sunSon,
			\timeScale, Pfunc({ thisThread.clock.beatDur }),
			keys, sunrisesSeq;
		);
	};

});
)

(
var keys, sunrises, firstJan, samplesBind, daysBind, sunrisesSeq, sunrisesBind, secsToFirstSunrise, restToFirstSunrise;


#firstJan, daysBind = ~makeDaysBind.("2022_CATA_01_US_every_day.csv");
samplesBind = ~makeSamplesBind.("2022_CATA_01_US.csv", firstJan);
sunrisesBind = ~makeSunrisesBind.("McCoy_sunrise_sunset_2022.csv", firstJan);

c = TempoClock(~to_secs[\week] * 4);
sunrisesBind.play(c);
//~combined = Ppar([daysBind, sunrisesBind]).play(c);
)

c.tempo = ~to_secs[\hour];
Env.perc( 1, 1, 1, -4).test.plot;
Env.perc( 1, 1, 1, -2).test.plot;
Env.perc( 1, 1, 1, 0).test.plot;
Env.perc( 1, 1, 1, 2).test.plot;
Env.perc( 1, 1, 1, 4).test.plot;
Env.perc(0.001, 1, 1, -4).test.plot;    // sharper attack
Env.perc(0.001, 1, 1, -8).test.plot;    // change curvature
Env.perc(1, 0.01, 1, 4).test.plot;    // reverse envelope


