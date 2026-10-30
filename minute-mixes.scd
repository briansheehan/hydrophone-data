(
s.waitForBoot({
	~to_secs = Dictionary.newFrom([hour: 60*60, day: 24*60*60, year: 365*24*60*60]);
	~rate = 20;
	~amp_scaling = 6;
	~metadata_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/output_metadata.csv";
	~audio_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/";

	~read_datetimes = { |filepath|
		var datetimes = CSVFileReader.read((filepath).resolveRelative,
			skipEmptyLines:true, skipBlanks:true);
		var col_names = datetimes.removeAt(0); //column headings.
		col_names = col_names.collect({|item, idx|
			item.asSymbol;
		});
		datetimes = datetimes.collect({|row, idx|
			[row[0].asInteger, row[1].asInteger, row[2].asInteger, row[3].asInteger,
				row[4].asInteger, row[5].asInteger, row[6].asInteger, row[7], row[8]];
		});
		[col_names, datetimes];
/*		datetime_objs = Array.fill(datetimes_csv.size, {|i|
			var row = datetimes_csv[i];
			// Date(row[0].asInteger, row[1].asInteger, row[2].asInteger, row[3].asInteger,
			// row[4].asInteger, row[5].asInteger, row[6].asInteger, 0);
			row[6].asInteger;
		});
		datetime_objs;*/
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

	SynthDef(\daySon, { |day_of_week, out=0|
		var osc = SinOsc.ar((60 + day_of_week).midicps);
		var env = EnvGen.kr(Env.perc, doneAction: Done.freeSelf);
		var sig = osc * env;
		day_of_week.postln;
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
	})
/*
	Excercise to explore using patterns. Build patterns to represent the data
	collection schedule of the river study:
	The daily pattern (every 15 mins for one minute)
	Every day during the study duration for that year.
	*/





});
)


(
var keys, datetimes;
#keys, datetimes = ~read_datetimes.("2022_CATA_01_US_every_day.csv");
d = Pseq(datetimes);
b = Pbind(
	\instrument, \daySon,
	keys, d;
);
)
//1 beat per day = 1 beat every 60*60*24 seconds 86400
60*60*24;

~to_secs[\year];
c = TempoClock(1/~to_secs[\year]);
c.tempo = c.tempo * 100;
~seq = b.play(c);
~seq.stop;
