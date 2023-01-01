
%size_t = type i64

declare dso_local noalias %object* @malloc(%size_t) "alloc-family"="malloc"
declare dso_local void @free(%object*) "alloc-family"="malloc"
declare dso_local i32 @printf(i8* noalias nocapture, ...)

%funptr = type %size_t*
%vtable = type { { %size_t, void(%object*)* }, [ 0 x %funptr ] }
%object = type { %vtable*, %size_t }
%lambda = type { %funptr, %object* }

@memoryCounter = internal global %size_t zeroinitializer
@formatstr = private unnamed_addr constant [11 x i8] c"Mem=%lld!\0A\00", align 1

@global_unit_vt = internal global { { void(%object*)*, %size_t }, [ 0 x %funptr ] } { { void(%object*)*, %size_t } { void(%object*)* null, %size_t 0 }, [ 0 x %funptr ] [ ] }
@global_unit = internal global %object { %vtable* bitcast({ { void(%object*)*, %size_t }, [ 0 x %funptr ] }* @global_unit_vt to %vtable*), %size_t 0 }



define dso_local i32 @main() {
    %result = tail call tailcc i32 @synth_main(%object* @global_unit)
    %param = getelementptr inbounds [11 x i8], [11 x i8]* @formatstr, i32 0, i32 0
    %count = load %size_t, %size_t* @memoryCounter
    %ignore = tail call i32 (i8*, ...) @printf(i8* %param, %size_t %count)
    ret i32 %result
}

define internal tailcc %object* @newObject(%size_t %p0, %vtable* %p1) {
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

define internal tailcc void @deleteObject(%size_t %p0, %object* %p1) {
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

define internal tailcc void @release(%object** %orefref) {
entry:
    %oref = load %object*, %object** %orefref
    store %object* null, %object** %orefref
    %is_null = icmp eq %object* null, %oref
    br i1 %is_null, label %skip, label %check_count
check_count:
    %refcnt_ptr = getelementptr %object, %object* %oref, i32 0, i32 1
    %refcnt = load %size_t, %size_t* %refcnt_ptr
    switch %size_t %refcnt, label %subtract [ %size_t 0, label %skip
                                              %size_t 1, label %dealloc ]
subtract:
; If count is greater than one, subject one
    %newcnt = sub %size_t %refcnt, 1
    store %size_t %newcnt, %size_t* %refcnt_ptr
    ret void
dealloc:
; If the count is one, this object is to be released now
    musttail call tailcc void @releaseActual(%object* %oref)
    ret void
skip:
; If the reference is null or the count is zero, skip the release
    ret void
}

define internal tailcc void @releaseMany(%object** %p0, %object** %p1) {
entry:
    %isEnd = icmp eq %object** %p0, %p1
    br i1 %isEnd, label %exit, label %iterate
iterate:
    call tailcc void @release(%object** %p0)
    %next = getelementptr %object*, %object** %p0, i32 1
    musttail call tailcc void @releaseMany(%object** %next, %object** %p1)
    ret void
exit:
    ret void
}

define internal tailcc void @acquire(%object* %p0) {
entry:
    %refcnt_ptr = getelementptr %object, %object* %p0, i32 0, i32 1
    %refcnt = load %size_t, %size_t* %refcnt_ptr
    switch %size_t %refcnt, label %add [ %size_t 0, label %skip ]
add:
; If count is non zero, add one
    %newcnt = add %size_t %refcnt, 1
    store %size_t %newcnt, %size_t* %refcnt_ptr
    ret void
skip:
; If the count is zero, this object can never be acquired
    ret void
}

define internal tailcc %funptr @lookupVirtualMethod(%object* %obj_ptr, %size_t %id) {
start:
    %vt_ptr_ptr = getelementptr %object, %object* %obj_ptr, i32 0, i32 0
    %vt_ptr = load %vtable*, %vtable** %vt_ptr_ptr
    %mask_ptr = getelementptr %vtable, %vtable* %vt_ptr, i32 0, i32 0, i32 0
    %mask = load %size_t, %size_t* %mask_ptr
    %id1 = sub %size_t %id, 1
    br label %loop

loop:
    %id2 = phi %size_t [ %id1, %start ], [ %index, %loop ]
    %id3 = add %size_t %id2, 1
    %index = and %size_t %mask, %id3

    %method_ptr_ptr = getelementptr %vtable, %vtable* %vt_ptr, i32 0, i32 1, %size_t %index
    %method_ptr = load %funptr, %funptr* %method_ptr_ptr
    %target_id_ptr = getelementptr %size_t, %size_t* %method_ptr, i32 -1
    %target_id = load %size_t, %size_t* %target_id_ptr

    %isneq = icmp ne %size_t %id, %target_id
    br i1 %isneq, label %loop, label %finish

finish:
    ret %funptr %method_ptr
}
