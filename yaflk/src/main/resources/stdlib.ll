
declare dso_local noalias %object* @malloc(...) "alloc-family"="malloc"
declare dso_local void @free(%object*) "alloc-family"="malloc"
declare dso_local i32 @printf(i8* noalias nocapture, ...)



%vtable = type { [ 0 x i8* ] }
%object = type { %vtable*, i8* }

@memoryCounter = internal global i64 zeroinitializer
@formatstr = private unnamed_addr constant [11 x i8] c"Mem=%lld!\0A\00", align 1



define dso_local i32 @main() noinline {
    %result = call i32 @synth_main()
    %param = getelementptr inbounds [11 x i8], [11 x i8]* @formatstr, i32 0, i32 0
    %count = load i64, i64* @memoryCounter
    %ignore = call i32 (i8*, ...) @printf(i8* %param, i64 %count)
    ret i32 %result
}

define internal %object* @create_object(i32 %p0, %vtable* %p1) noinline {
    %sext = sext i32 %p0 to i64
    atomicrmw add i64* @memoryCounter, i64 %sext acquire

    %which = icmp eq i32 ptrtoint(i8** getelementptr(i8*, i8** null, i32 1) to i32), 4
    br i1 %which, label %if32, label %if64
if32:
    %r1 = call %object* (...) @malloc(i32 %p0)
    br label %end
if64:
    %p0big = sext i32 %p0 to i64
    %r2 = call %object* (...) @malloc(i64 %p0big)
    br label %end
end:
    %res = phi %object* [ %r1, %if32 ], [ %r2, %if64 ]
    %res_1 = getelementptr %object, %object* %res, i32 0, i32 0
    store %vtable* %p1, %vtable** %res_1
    %res_2 = getelementptr %object, %object* %res, i32 0, i32 1
    store i8* inttoptr(i32 1 to i8*), i8** %res_2
    ret %object* %res
}

define internal void @delete_object(i32 %p0, %object* %p1) noinline {
    %sext = sext i32 %p0 to i64
    atomicrmw sub i64* @memoryCounter, i64 %sext acquire

    call void @free(%object* %p1)
    ret void
}

define internal void @releaseActual(%object* %p0) noinline {
    %dealloc_1 = getelementptr %object, %object* %p0, i32 0, i32 0
    %dealloc_2 = load %vtable*, %vtable** %dealloc_1
    %dealloc_3 = getelementptr %vtable, %vtable* %dealloc_2, i32 0, i32 0, i32 0
    %dealloc_4 = load i8*, i8** %dealloc_3
    %dealloc_5 = bitcast i8* %dealloc_4 to void(%object*)*
    call void %dealloc_5(%object* %p0)
    ret void
}

define internal void @releaseAtomic(%object* %p0) noinline {
entry:
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %countStart = load i8*, i8** %countPointer
    br label %loop
loop:
    %count = phi i8* [ %countStart, %entry ], [ %original, %loop ]
    %dec = getelementptr i8, i8* %count, i32 -1
    %val_success = cmpxchg i8** %countPointer, i8* %count, i8* %dec acq_rel monotonic
    %original = extractvalue { i8*, i1 } %val_success, 0
    %success = extractvalue { i8*, i1 } %val_success, 1
    br i1 %success, label %done, label %loop, !prof !{!"branch_weights", i32 1, i32 0}
done:
    %isDownToOne = icmp eq i8* %original, inttoptr(i32 1 to i8*)
    br i1 %isDownToOne, label %dealloc, label %return, !prof !{!"branch_weights", i32 1, i32 0}
dealloc:
    musttail call void @releaseActual(%object* %p0)
    ret void
return:
    ret void

}

define internal void @release(%object* %p0) noinline {
entry:
    %isNull = icmp eq %object* null, %p0
    br i1 %isNull, label %return, label %notNull, !prof !{!"branch_weights", i32 0, i32 1}
notNull:
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %countStart = load i8*, i8** %countPointer
    %isOne = icmp eq i8* %countStart, inttoptr(i32 1 to i8*)
    br i1 %isOne, label %dealloc, label %atomic, !prof !{!"branch_weights", i32 1, i32 0}
dealloc:
    musttail call void @releaseActual(%object* %p0)
    ret void
atomic:
    musttail call void @releaseAtomic(%object* %p0)
    ret void
return:
    ret void
}

define internal void @acquireAtomic(%object* %p0) noinline {
entry:
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %countStart = load i8*, i8** %countPointer
    br label %loop
loop:
    %count = phi i8* [ %countStart, %entry ], [ %original, %loop ]
    %inc = getelementptr i8, i8* %count, i32 1
    %val_success = cmpxchg i8** %countPointer, i8* %count, i8* %inc acq_rel monotonic
    %original = extractvalue { i8*, i1 } %val_success, 0
    %success = extractvalue { i8*, i1 } %val_success, 1
    br i1 %success, label %done, label %loop, !prof !{!"branch_weights", i32 1, i32 0}
done:
    ret void
}

define internal void @acquire(%object* %p0) noinline {
entry:
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %countStart = load i8*, i8** %countPointer
    %isOne = icmp eq i8* %countStart, inttoptr(i32 1 to i8*)
    br i1 %isOne, label %setTwo, label %done, !prof !{!"branch_weights", i32 1, i32 0}
setTwo:
    store i8* inttoptr(i32 2 to i8*), i8** %countPointer
    ret void
done:
    musttail call void @acquireAtomic(%object* %p0)
    ret void
}

