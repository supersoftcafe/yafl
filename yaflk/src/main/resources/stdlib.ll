
declare dso_local noalias %object* @malloc(...) "alloc-family"="malloc"
declare dso_local void @free(%object*) "alloc-family"="malloc"

%vtable = type { [ 0 x i8* ] }
%object = type { %vtable*, i8* }


define internal %object* @alloc(i32 %p0, %vtable* %p1) {
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

define internal void @acquire(%object* %p0) {
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %count = load i8*, i8** %countPointer
    %isOne = icmp eq i8* %count, inttoptr(i32 1 to i8*)
    br i1 %isOne, label %justWriteTwo, label %atomic
justWriteTwo:
    store i8* inttoptr(i32 2 to i8*), i8** %countPointer
    br label %end
atomic:
    %which = icmp eq i32 ptrtoint(i8** getelementptr(i8*, i8** null, i32 1) to i32), 4
    br i1 %which, label %if32, label %if64
if32:
    %if32_1 = bitcast i8** %countPointer to i32*
    %if32_2 = atomicrmw add i32* %if32_1, i32 1 acquire
    br label %end
if64:
    %if64_1 = bitcast i8** %countPointer to i64*
    %if64_2 = atomicrmw add i64* %if64_1, i64 1 acquire
    br label %end
end:
    ret void
}

define internal void @release(%object* %p0) {
    %isNull = icmp eq %object* null, %p0
    br i1 %isNull, label %end, label %notNull
notNull:
    %countPointer = getelementptr %object, %object* %p0, i32 0, i32 1
    %count = load i8*, i8** %countPointer
    %isOne = icmp eq i8* %count, inttoptr(i32 1 to i8*)
    br i1 %isOne, label %dealloc, label %test
test:
    %which = icmp eq i32 ptrtoint(i8** getelementptr(i8*, i8** null, i32 1) to i32), 4
    br i1 %which, label %if32, label %if64
if32:
    %if32_2 = bitcast i8** %countPointer to i32*
    %if32_3 = atomicrmw sub i32* %if32_2, i32 1 acquire
    %if32_4 = icmp eq i32 %if32_3, 1
    br i1 %if32_4, label %dealloc, label %end
if64:
    %if64_2 = bitcast i8** %countPointer to i64*
    %if64_3 = atomicrmw sub i64* %if64_2, i64 1 acquire
    %if64_4 = icmp eq i64 %if64_3, 1
    br i1 %if64_4, label %dealloc, label %end
dealloc:
    %dealloc_1 = getelementptr %object, %object* %p0, i32 0, i32 0
    %dealloc_2 = load %vtable*, %vtable** %dealloc_1
    %dealloc_3 = getelementptr %vtable, %vtable* %dealloc_2, i32 0, i32 0, i32 0
    %dealloc_4 = load i8*, i8** %dealloc_3
    %dealloc_5 = bitcast i8* %dealloc_4 to void(%object*)*
    call void %dealloc_5(%object* %p0)
    ret void
end:
    ret void
}

