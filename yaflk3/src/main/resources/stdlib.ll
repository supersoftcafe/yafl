

%int    = type i32
%size_t = type i64

declare dso_local noalias noundef ptr @malloc(%size_t noundef) local_unnamed_addr "alloc-family"="malloc"
declare dso_local void @free(ptr allocptr nocapture noundef) local_unnamed_addr "alloc-family"="malloc"
declare dso_local i32 @printf(i8* noalias nocapture, ...)
declare dso_local void @abort()

%funptr = type ptr
%vtable = type { { %size_t, ptr }, [ 0 x %funptr ] }
%object = type { ptr, %size_t }

@arrayerrorstr = private unnamed_addr constant [12 x i8] c"Array index\00", align 1
@global_unit = external global %object, align 8


declare dso_local i32 @runtime_main(ptr)
declare dso_local ptr @heap_alloc(%size_t) local_unnamed_addr "alloc-family"="yafl"
declare dso_local void @heap_free(%size_t, ptr nocapture) local_unnamed_addr "alloc-family"="yafl"
declare dso_local ptr @obj_create(%size_t, %vtable*)
declare dso_local void @obj_acquire(ptr)
declare dso_local void @obj_release(ptr)
declare dso_local void @log_error(ptr nocapture)
declare dso_local void @log_error_and_exit(ptr nocapture, ...) noreturn
declare dso_local void @fiber_parallel(ptr noundef, ptr noundef, %size_t noundef)








define internal void @assertWithMessage(i1 %cond, ptr %msg) {
    br i1 %cond, label %cond_ok, label %cond_bad
cond_bad:
    call void @log_error_and_exit(ptr %msg) noreturn
    ret void
cond_ok:
    ret void
}

define internal void @checkArrayAccess(i32 %index, i32 %size) {
    %arrayCheck = icmp uge i32 %index, %size
    br i1 %arrayCheck, label %bounds_bad, label %bounds_ok
bounds_bad:
    %param = getelementptr inbounds [12 x i8], [12 x i8]* @arrayerrorstr, i32 0, i32 0
    call void @log_error_and_exit(i8* %param) noreturn
    ret void
bounds_ok:
    ret void
}

define internal void @obj_releaseRef(%object** %orefref) {
entry:
    %oref = load %object*, %object** %orefref
    %is_null = icmp eq %object* null, %oref
    br i1 %is_null, label %skip, label %check_count
check_count:
    store %object* null, %object** %orefref
    musttail call void @obj_release(%object* %oref)
    ret void
skip:
    ret void
}

define internal %funptr @lookupVirtualMethod(%object* %obj_ptr, %size_t %id) {
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

define dso_local i32 @main2() {
    %result = tail call i32 @synth_main(ptr @global_unit)
    ret i32 %result
}

define dso_local i32 @main() {
    %result = tail call i32 @runtime_main(ptr @main2)
    ret i32 %result
}
