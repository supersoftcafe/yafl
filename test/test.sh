
mkdir -p build

export YAFL_PATH="src"
# export DEBUG="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=10042"
export DEBUG=""
java $DEBUG -cp ../yaflk3/build/libs/yaflk3-1.0-SNAPSHOT-standalone.jar MainKt $* >build/raw.ll || exit 1

# Create optimized version
# cp build/raw.ll build/opt.ll
# clang -O3 -S -emit-llvm build/opt.ll || exit 1
opt -O3 -S -o build/opt.ll build/raw.ll || exit 1

# Create optimized assembly version
llc -O=3 build/opt.ll || exit 1

# Compile and link with library
# llc -filetype=obj -O=3 build/opt.ll || exit 1
clang -O3 -o build/main build/raw.ll ../yaflc1/libyaflc1.a || exit 1


