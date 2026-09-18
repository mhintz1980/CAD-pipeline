# Both wrappers still have broken downloader (14:08 EDT inspection)
tools/astra_modal_engine.py AND tools/astra_modal_wide.py STILL use `with vol_out.read_file(o['path']) as data:`. Priorreports claimingfixedarewrong; actualcurrentfilecontainsbug. read_file returns ITERATORofbytes, NOT contextmanager andnotbytes.

Correct algorithm: remotevolume-relativepath (strip /output/ forengine; strip /out/ forwide), openlocaltargetwb, iterate `for chunk in vol_out.read_file(remote_relative_path): local_file.write(chunk)`. Do notwritegeneratorobject; no withonread_file. Localrelativepath must be relative UNIQUE run outputroot, notvolume root nestedrun twice. Use pathlib.PurePosixPath forcloudpath onWindows or simpleknownprefixremove. Keep allretrievedartifacts scopewithinlocalrunfolder.

Actualjobsneednotbererun ifdownloadfails: outputsarealreadycommittedonModalVolume. Recoverwithstreamreador`modal volume get`using--help. No extraheavyrerunjustfordownload. Patchownwrapperafterdispatch ifalreadyrunning; recoverreceiptoutputsaftercompletion. Hardfaildownloaderror, neverclaimsuccesswhenonlypreflightlogsretrieved.
