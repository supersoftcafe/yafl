
mkdir -p build

java -cp ../yaflk3/out/artifacts/yaflk3_jar/yaflk3.jar MainKt src/*.yafl >build/raw.ll || exit 1

# Create optimized version
# cp build/raw.ll build/opt.ll
# clang -O3 -S -emit-llvm build/opt.ll || exit 1
opt -O3 -S -o build/opt.ll build/raw.ll || exit 1

# Create optimized assembly version
llc -O=3 build/opt.ll || exit 1

# Compile and link with library
# llc -filetype=obj -O=3 build/opt.ll || exit 1
clang -O0 -g -o build/main build/raw.ll ../yaflc1/cmake-build-debug/libyaflc1.a


