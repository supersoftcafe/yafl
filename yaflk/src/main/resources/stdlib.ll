
%size_t = type i64

declare dso_local noalias %object* @malloc(%size_t) "alloc-family"="malloc"
declare dso_local void @free(%object*) "alloc-family"="malloc"
declare dso_local i32 @printf(i8* noalias nocapture, ...)

%vtable = type { [ 0 x i8* ] }
%object = type { %vtable*, %size_t }
%lambda = type { i8*, %object* }

@memoryCounter = internal global %size_t zeroinitializer
@formatstr = private unnamed_addr constant [11 x i8] c"Mem=%lld!\0A\00", align 1



define dso_local i32 @main() {
    %result = call i32 @synth_main()
    %param = getelementptr inbounds [11 x i8], [11 x i8]* @formatstr, i32 0, i32 0
    %count = load %size_t, %size_t* @memoryCounter
    %ignore = call i32 (i8*, ...) @printf(i8* %param, %size_t %count)
    ret i32 %result
}

define internal %object* @create_object(%size_t %p0, %vtable* %p1) {
;    atomicrmw add %size_t* @memoryCounter, %size_t %p0 acquire
    %old = load %size_t, %size_t* @memoryCounter
    %new = add %size_t %old, %p0
    store %size_t %new, %size_t* @memoryCounter

    %result = call %object* @malloc(%size_t %p0)
    %vtable_ptr = getelementptr %object, %object* %result, i32 0, i32 0
    store %vtable* %p1, %vtable** %vtable_ptr
    %refcnt_ptr = getelementptr %object, %object* %result, i32 0, i32 1
    store %size_t 1, %size_t* %refcnt_ptr
    ret %object* %result
}

define internal void @delete_object(%size_t %p0, %object* %p1) {
;    atomicrmw sub %size_t* @memoryCounter, %size_t %p0 acquire
    %old = load %size_t, %size_t* @memoryCounter
    %new = sub %size_t %old, %p0
    store %size_t %new, %size_t* @memoryCounter

    call void @free(%object* %p1)
    ret void
}



define internal void @releaseActual(%object* %p0) {
    %dealloc_1 = getelementptr %object, %object* %p0, i32 0, i32 0
    %dealloc_2 = load %vtable*, %vtable** %dealloc_1
    %dealloc_3 = getelementptr %vtable, %vtable* %dealloc_2, i32 0, i32 0, i32 0
    %dealloc_4 = load i8*, i8** %dealloc_3
    %dealloc_5 = bitcast i8* %dealloc_4 to void(%object*)*
    musttail call void %dealloc_5(%object* %p0)
    ret void
}

define internal void @release(%object* %p0) {
entry:
    %isNull = icmp eq %object* null, %p0
    br i1 %isNull, label %return, label %notNull, !prof !{!"branch_weights", i32 0, i32 1}
notNull:
    %refcnt_ptr = getelementptr %object, %object* %p0, i32 0, i32 1

;    %old = atomicrmw sub %size_t* %refcnt_ptr, %size_t 1 acquire
;    %isOne = icmp eq %size_t %old, 1

    %old = load %size_t, %size_t* %refcnt_ptr
    %new = sub %size_t %old, 1
    store %size_t %new, %size_t* %refcnt_ptr
    %isOne = icmp eq %size_t %new, 0

    br i1 %isOne, label %dealloc, label %return, !prof !{!"branch_weights", i32 1, i32 0}
dealloc:
    musttail call void @releaseActual(%object* %p0)
    ret void
return:
    ret void
}

define internal void @acquire(%object* %p0) {
entry:
    %isNull = icmp eq %object* null, %p0
    br i1 %isNull, label %return, label %notNull, !prof !{!"branch_weights", i32 0, i32 1}
notNull:
    %refcnt_ptr = getelementptr %object, %object* %p0, i32 0, i32 1

;    %old = atomicrmw add %size_t* %refcnt_ptr, %size_t 1 acquire

    %old = load %size_t, %size_t* %refcnt_ptr
    %new = add %size_t %old, 1
    store %size_t %new, %size_t* %refcnt_ptr

    ret void
return:
    ret void
}

