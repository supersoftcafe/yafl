# CMAKE generated file: DO NOT EDIT!
# Generated by "Unix Makefiles" Generator, CMake Version 3.25

# Delete rule output on recipe failure.
.DELETE_ON_ERROR:

#=============================================================================
# Special targets provided by cmake.

# Disable implicit rules so canonical targets will work.
.SUFFIXES:

# Disable VCS-based implicit rules.
% : %,v

# Disable VCS-based implicit rules.
% : RCS/%

# Disable VCS-based implicit rules.
% : RCS/%,v

# Disable VCS-based implicit rules.
% : SCCS/s.%

# Disable VCS-based implicit rules.
% : s.%

.SUFFIXES: .hpux_make_needs_suffix_list

# Command-line flag to silence nested $(MAKE).
$(VERBOSE)MAKESILENT = -s

#Suppress display of executed commands.
$(VERBOSE).SILENT:

# A target that is always out of date.
cmake_force:
.PHONY : cmake_force

#=============================================================================
# Set environment variables for the build.

# The shell in which to execute make rules.
SHELL = /bin/sh

# The CMake executable.
CMAKE_COMMAND = /usr/local/Cellar/cmake/3.25.1/bin/cmake

# The command to remove a file.
RM = /usr/local/Cellar/cmake/3.25.1/bin/cmake -E rm -f

# Escaping for special characters.
EQUALS = =

# The top-level source directory on which CMake was run.
CMAKE_SOURCE_DIR = /Users/mbrown/Projects/yafl/yaflc1

# The top-level build directory on which CMake was run.
CMAKE_BINARY_DIR = /Users/mbrown/Projects/yafl/yaflc1

# Include any dependencies generated for this target.
include CMakeFiles/yaflc1.dir/depend.make
# Include any dependencies generated by the compiler for this target.
include CMakeFiles/yaflc1.dir/compiler_depend.make

# Include the progress variables for this target.
include CMakeFiles/yaflc1.dir/progress.make

# Include the compile flags for this target's objects.
include CMakeFiles/yaflc1.dir/flags.make

CMakeFiles/yaflc1.dir/main.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/main.c.o: main.c
CMakeFiles/yaflc1.dir/main.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_1) "Building C object CMakeFiles/yaflc1.dir/main.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/main.c.o -MF CMakeFiles/yaflc1.dir/main.c.o.d -o CMakeFiles/yaflc1.dir/main.c.o -c /Users/mbrown/Projects/yafl/yaflc1/main.c

CMakeFiles/yaflc1.dir/main.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/main.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/main.c > CMakeFiles/yaflc1.dir/main.c.i

CMakeFiles/yaflc1.dir/main.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/main.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/main.c -o CMakeFiles/yaflc1.dir/main.c.s

CMakeFiles/yaflc1.dir/fiber.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/fiber.c.o: fiber.c
CMakeFiles/yaflc1.dir/fiber.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_2) "Building C object CMakeFiles/yaflc1.dir/fiber.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/fiber.c.o -MF CMakeFiles/yaflc1.dir/fiber.c.o.d -o CMakeFiles/yaflc1.dir/fiber.c.o -c /Users/mbrown/Projects/yafl/yaflc1/fiber.c

CMakeFiles/yaflc1.dir/fiber.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/fiber.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/fiber.c > CMakeFiles/yaflc1.dir/fiber.c.i

CMakeFiles/yaflc1.dir/fiber.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/fiber.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/fiber.c -o CMakeFiles/yaflc1.dir/fiber.c.s

CMakeFiles/yaflc1.dir/context.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/context.c.o: context.c
CMakeFiles/yaflc1.dir/context.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_3) "Building C object CMakeFiles/yaflc1.dir/context.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/context.c.o -MF CMakeFiles/yaflc1.dir/context.c.o.d -o CMakeFiles/yaflc1.dir/context.c.o -c /Users/mbrown/Projects/yafl/yaflc1/context.c

CMakeFiles/yaflc1.dir/context.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/context.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/context.c > CMakeFiles/yaflc1.dir/context.c.i

CMakeFiles/yaflc1.dir/context.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/context.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/context.c -o CMakeFiles/yaflc1.dir/context.c.s

CMakeFiles/yaflc1.dir/queue.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/queue.c.o: queue.c
CMakeFiles/yaflc1.dir/queue.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_4) "Building C object CMakeFiles/yaflc1.dir/queue.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/queue.c.o -MF CMakeFiles/yaflc1.dir/queue.c.o.d -o CMakeFiles/yaflc1.dir/queue.c.o -c /Users/mbrown/Projects/yafl/yaflc1/queue.c

CMakeFiles/yaflc1.dir/queue.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/queue.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/queue.c > CMakeFiles/yaflc1.dir/queue.c.i

CMakeFiles/yaflc1.dir/queue.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/queue.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/queue.c -o CMakeFiles/yaflc1.dir/queue.c.s

CMakeFiles/yaflc1.dir/blitz.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/blitz.c.o: blitz.c
CMakeFiles/yaflc1.dir/blitz.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_5) "Building C object CMakeFiles/yaflc1.dir/blitz.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/blitz.c.o -MF CMakeFiles/yaflc1.dir/blitz.c.o.d -o CMakeFiles/yaflc1.dir/blitz.c.o -c /Users/mbrown/Projects/yafl/yaflc1/blitz.c

CMakeFiles/yaflc1.dir/blitz.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/blitz.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/blitz.c > CMakeFiles/yaflc1.dir/blitz.c.i

CMakeFiles/yaflc1.dir/blitz.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/blitz.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/blitz.c -o CMakeFiles/yaflc1.dir/blitz.c.s

CMakeFiles/yaflc1.dir/heap.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/heap.c.o: heap.c
CMakeFiles/yaflc1.dir/heap.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_6) "Building C object CMakeFiles/yaflc1.dir/heap.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/heap.c.o -MF CMakeFiles/yaflc1.dir/heap.c.o.d -o CMakeFiles/yaflc1.dir/heap.c.o -c /Users/mbrown/Projects/yafl/yaflc1/heap.c

CMakeFiles/yaflc1.dir/heap.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/heap.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/heap.c > CMakeFiles/yaflc1.dir/heap.c.i

CMakeFiles/yaflc1.dir/heap.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/heap.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/heap.c -o CMakeFiles/yaflc1.dir/heap.c.s

CMakeFiles/yaflc1.dir/object.c.o: CMakeFiles/yaflc1.dir/flags.make
CMakeFiles/yaflc1.dir/object.c.o: object.c
CMakeFiles/yaflc1.dir/object.c.o: CMakeFiles/yaflc1.dir/compiler_depend.ts
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_7) "Building C object CMakeFiles/yaflc1.dir/object.c.o"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -MD -MT CMakeFiles/yaflc1.dir/object.c.o -MF CMakeFiles/yaflc1.dir/object.c.o.d -o CMakeFiles/yaflc1.dir/object.c.o -c /Users/mbrown/Projects/yafl/yaflc1/object.c

CMakeFiles/yaflc1.dir/object.c.i: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Preprocessing C source to CMakeFiles/yaflc1.dir/object.c.i"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -E /Users/mbrown/Projects/yafl/yaflc1/object.c > CMakeFiles/yaflc1.dir/object.c.i

CMakeFiles/yaflc1.dir/object.c.s: cmake_force
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green "Compiling C source to assembly CMakeFiles/yaflc1.dir/object.c.s"
	/Library/Developer/CommandLineTools/usr/bin/cc $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -S /Users/mbrown/Projects/yafl/yaflc1/object.c -o CMakeFiles/yaflc1.dir/object.c.s

# Object files for target yaflc1
yaflc1_OBJECTS = \
"CMakeFiles/yaflc1.dir/main.c.o" \
"CMakeFiles/yaflc1.dir/fiber.c.o" \
"CMakeFiles/yaflc1.dir/context.c.o" \
"CMakeFiles/yaflc1.dir/queue.c.o" \
"CMakeFiles/yaflc1.dir/blitz.c.o" \
"CMakeFiles/yaflc1.dir/heap.c.o" \
"CMakeFiles/yaflc1.dir/object.c.o"

# External object files for target yaflc1
yaflc1_EXTERNAL_OBJECTS =

libyaflc1.a: CMakeFiles/yaflc1.dir/main.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/fiber.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/context.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/queue.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/blitz.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/heap.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/object.c.o
libyaflc1.a: CMakeFiles/yaflc1.dir/build.make
libyaflc1.a: CMakeFiles/yaflc1.dir/link.txt
	@$(CMAKE_COMMAND) -E cmake_echo_color --switch=$(COLOR) --green --bold --progress-dir=/Users/mbrown/Projects/yafl/yaflc1/CMakeFiles --progress-num=$(CMAKE_PROGRESS_8) "Linking C static library libyaflc1.a"
	$(CMAKE_COMMAND) -P CMakeFiles/yaflc1.dir/cmake_clean_target.cmake
	$(CMAKE_COMMAND) -E cmake_link_script CMakeFiles/yaflc1.dir/link.txt --verbose=$(VERBOSE)

# Rule to build all files generated by this target.
CMakeFiles/yaflc1.dir/build: libyaflc1.a
.PHONY : CMakeFiles/yaflc1.dir/build

CMakeFiles/yaflc1.dir/clean:
	$(CMAKE_COMMAND) -P CMakeFiles/yaflc1.dir/cmake_clean.cmake
.PHONY : CMakeFiles/yaflc1.dir/clean

CMakeFiles/yaflc1.dir/depend:
	cd /Users/mbrown/Projects/yafl/yaflc1 && $(CMAKE_COMMAND) -E cmake_depends "Unix Makefiles" /Users/mbrown/Projects/yafl/yaflc1 /Users/mbrown/Projects/yafl/yaflc1 /Users/mbrown/Projects/yafl/yaflc1 /Users/mbrown/Projects/yafl/yaflc1 /Users/mbrown/Projects/yafl/yaflc1/CMakeFiles/yaflc1.dir/DependInfo.cmake --color=$(COLOR)
.PHONY : CMakeFiles/yaflc1.dir/depend

