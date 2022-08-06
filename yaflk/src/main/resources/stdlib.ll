
%size_t = type i64

declare dso_local noalias %object* @malloc(%size_t) "alloc-family"="malloc"
declare dso_local void @free(%object*) "alloc-family"="malloc"
declare dso_local i32 @printf(i8* noalias nocapture, ...)

%vtable = type { { %size_t, void(%object*)* }, [ 0 x %size_t* ] }
%object = type { %vtable*, %size_t }
%lambda = type { %size_t*, %object* }

@memoryCounter = internal global %size_t zeroinitializer
@formatstr = private unnamed_addr constant [11 x i8] c"Mem=%lld!\0A\00", align 1



define dso_local i32 @main() {
    %result = tail call tailcc i32 @synth_main(%object* null)
    %param = getelementptr inbounds [11 x i8], [11 x i8]* @formatstr, i32 0, i32 0
    %count = load %size_t, %size_t* @memoryCounter
    %ignore = tail call i32 (i8*, ...) @printf(i8* %param, %size_t %count)
    ret i32 %result
}

define internal tailcc %object* @create_object(%size_t %p0, %vtable* %p1) {
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

define internal tailcc void @delete_object(%size_t %p0, %object* %p1) {
;    atomicrmw sub %size_t* @memoryCounter, %size_t %p0 acquire
    %old = load %size_t, %size_t* @memoryCounter
    %new = sub %size_t %old, %p0
    store %size_t %new, %size_t* @memoryCounter

    call void @free(%object* %p1)
    ret void
}



define internal tailcc void @releaseActual(%object* %p0) {
    %dealloc_1 = getelementptr %object, %object* %p0, i32 0, i32 0
    %dealloc_2 = load %vtable*, %vtable** %dealloc_1
    %dealloc_3 = getelementptr %vtable, %vtable* %dealloc_2, i32 0, i32 0, i32 1
    %dealloc_4 = load void(%object*)*, void(%object*)** %dealloc_3
    musttail call tailcc void %dealloc_4(%object* %p0)
    ret void
}

define internal tailcc void @release(%object* %p0) {
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
    musttail call tailcc void @releaseActual(%object* %p0)
    ret void
return:
    ret void
}

define internal tailcc void @acquire(%object* %p0) {
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

define internal tailcc %lambda @lookup_virtual_method(%object* %obj_ptr, %size_t %id) {
start:
    %vt_ptr_ptr = getelementptr %object, %object* %obj_ptr, i32 0, i32 0
    %vt_ptr = load %vtable*, %vtable** %vt_ptr_ptr
    %mask_ptr = getelementptr %vtable, %vtable* %vt_ptr, i32 0, i32 0, i32 0
    %mask = load %size_t, %size_t* %mask_ptr
    br label %loop

loop:
    %id2 = phi %size_t [ %id, %start ], [ %index, %loop ]
    %id3 = add %size_t %id2, 1
    %index = and %size_t %mask, %id3

    %method_ptr_ptr = getelementptr %vtable, %vtable* %vt_ptr, i32 0, i32 1, %size_t %index
    %method_ptr = load %size_t*, %size_t** %method_ptr_ptr
    %target_id_ptr = getelementptr %size_t, %size_t* %method_ptr, i32 -1
    %target_id = load %size_t, %size_t* %target_id_ptr

    %isneq = icmp ne %size_t %id, %target_id
    br i1 %isneq, label %loop, label %finish

finish:
    %result1 = insertvalue %lambda undef, %size_t* %method_ptr, 0
    %result2 = insertvalue %lambda %result1, %object* %obj_ptr, 1
    ret %lambda %result2
}
