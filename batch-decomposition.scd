(
s.waitForBoot({
    // Store the location of the FluCoMa audio files in the audioFiles variable
    //var audioFiles = PathName(File.realpath(FluidDataSet.class.filenameSymbol).dirname.withTrailingSlash ++ "../Resources/AudioFiles/");
	var audioFiles = PathName(PathName(thisProcess.nowExecutingPath).parentPath ++ "2021_CATA_01_US/wavs");
    // Create a dictionary that will contain the resulting buffer, associated to a string which represents the original source file
    ~results = Dictionary.new;
	audioFiles.postln;

    // In the language iterate over all the files in the example audio files directory
    audioFiles.files.do({ |file| // Individual file paths are now this variable
        if ((file.extension == "wav"), { // Only process wav files
            var src = Buffer.read(s, file.fullPath.asString); // Create a buffer with the source audio in a buffer called "src"
            // Create two buffers, h and p for the harmonic and percussive outputs respectively
            var h = Buffer.new(s);
            var p = Buffer.new(s);
            // Create a new buffer that we will compose into so harmonic and percussive exist in a two-channel buffer, rather than two separate mono buffers.
            var result = Buffer.new(s);

            ("Processing:"+file.fileName.asString).postln;
            // Do the HPSS processing. Only process the first channel to simplify things when we process a stereo file.
            // We call the processBlocking method in order to do synchronous calls that will happen in a deterministic order.
            // Later on you will see the process method being used to do asynchronous calls between the language and server.
            FluidBufHPSS.processBlocking(s, source:src, harmonic:h, percussive:p, numChans:1);
            FluidBufCompose.processBlocking(s, source:h, destination:result, destStartChan:0);
            FluidBufCompose.processBlocking(s, source:p, destination:result, destStartChan:1);

            // The three calls above are executed syncrhonously, but we need to sync to the server before we progressing to the next file in the loop.
            s.sync;

            // Associate the source file name (as a symbol) to the 2-channel result buffer.
            ~results.add(file.fileName.asSymbol -> result);

            // Free temporary buffers from the server
            src.free; h.free; p.free;
        });
    });
    // This is the entire dictionary of results.
    ~results.keys.do({ |key|
        (key++": "++~results[key].asString).postln;
    });

});
)
//~results.values.at(0).play;
(
{
    // PlayBuf with 2 channels, then pick channel 0 (left) or 1 (right)
	var fst_buf = ~results.values.at(1);
    var sig = PlayBuf.ar(fst_buf.numChannels, fst_buf, BufRateScale.kr(fst_buf));
    sig = sig[0]; // Select channel 0 (change to [1] for the right channel)
    Out.ar(0, sig ! 2); // Duplicate mono out to stereo speakers
}.play;
)

(
{
    // PlayBuf with 2 channels, then pick channel 0 (left) or 1 (right)
	var fst_buf = ~results.values.at(1);
    var sig = PlayBuf.ar(fst_buf.numChannels, fst_buf, BufRateScale.kr(fst_buf));
    sig = sig[1]; // Select channel 0 (change to [1] for the right channel)
    Out.ar(0, sig ! 2); // Duplicate mono out to stereo speakers
}.play;
)