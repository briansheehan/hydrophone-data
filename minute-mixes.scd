(
s.waitForBoot({
	~rate = 10;
	~metadata_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/output_metadata.csv";
	~audio_path = "/home/brian/Data/Stationary Hydrophone Data Collected in the Upper Colorado River, Colorado, 2021-24/2022 Test/";

	~read_metadata = { |path|
		CSVFileReader.read(~metadata_path, skipEmptyLines:true, skipBlanks:true);
	};

	SynthDef(\sineSynth, { |freq=440, in=0, out=0|
		var osc, amp;
		amp = In.kr(in);
		osc = SinOsc.ar(freq) * amp;
		Out.ar(out, osc.dup);
	}).add;

	SynthDef(\playBuffer, { |out=0, buf|
		var sig, amp;
		sig = PlayBuf.ar(2, buf, rate:~rate, doneAction: Done.freeSelf);
		amp = Amplitude.kr(sig);
		Out.kr(out, amp);
		Out.ar(out, sig);
	}).add;

	SynthDef(\ampFollower, { |in=0, out=0|
		var sig_in = In.ar(in);
		var amp = Amplitude.kr(sig_in);
		Out.kr(out, amp);

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
			name.postln;
			a = Synth(\playBuffer, [\buf, buf]);
			//b = Synth.after(a, \ampFollower);
			c = Synth.after(a, \sineSynth, [\freq, num_wavs/5]);
			(buf.duration/~rate).wait; // Wait until the current buffer finishes
			c.free;
			//b.free;
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