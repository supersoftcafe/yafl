
declare dso_local noalias i8* @malloc(...)

define internal i8* @alloc(i32 %p0) {
    %szp = getelementptr i8*, i8** null, i32 1
    %sz = ptrtoint i8** %szp to i32
    %which = icmp eq i32 %sz, 4
    br i1 %which, label %if32, label %if64
if32:
    %r1 = call i8* (...) @malloc(i32 %p0)
    br label %end
if64:
    %p0big = sext i32 %p0 to i64
    %r2 = call i8* (...) @malloc(i64 %p0big)
    br label %end
end:
    %res = phi i8* [ %r1, %if32 ], [ %r2, %if64 ]
    ret i8* %res
}

