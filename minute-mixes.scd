(
s.waitForBoot({
	~rate = 10;
	~amp_scaling = 3;
	~metadata_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/output_metadata.csv";
	~audio_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/";

	~read_metadata = { |path|
		CSVFileReader.read(~metadata_path, skipEmptyLines:true, skipBlanks:true);
	};

	SynthDef(\sineSynth, { |freq=440, amp=1, kr_in=0, out=0|
		var osc, amp_env;
		amp_env = In.kr(kr_in);
		osc = SinOsc.ar(freq) * amp * amp_env;
		Out.ar(out, osc.dup);
	}).add;

	SynthDef(\playBuffer, { |out=0, kr_out=0, buf, attackTime=0.7, releaseTime=0.7|
		var sig, amp;
		#l,r = PlayBuf.ar(2, buf, rate:~rate, doneAction: Done.freeSelf);
		amp = Amplitude.kr(r, 0.7, attackTime:attackTime, releaseTime:releaseTime);
		Out.kr(kr_out, amp);
		Out.ar(out, r.dup);
	}).add;

	~minute_mixes = Routine({
		var metadata_2D_array = ~read_metadata.value(~metadata_path);
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
			a = Synth(\playBuffer, [\buf, buf]);
			b = Synth.after(a, \sineSynth, [\freq, num_wavs/5, \amp, amp]);
			(buf.duration/~rate).wait; // Wait until the current buffer finishes
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
});
)

~minute_mixes.play;