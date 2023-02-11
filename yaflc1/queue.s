	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 11, 0
	.globl	_queue_init                     ## -- Begin function queue_init
	.p2align	4, 0x90
_queue_init:                            ## @queue_init
	.cfi_startproc
## %bb.0:
	pushq	%rax
	.cfi_def_cfa_offset 16
	movq	%rdi, _QUEUE_SIZE(%rip)
	callq	_malloc
	movq	%rax, _queue(%rip)
	testq	%rax, %rax
	je	LBB0_2
## %bb.1:
	popq	%rax
	retq
LBB0_2:
	leaq	L_.str(%rip), %rdi
	callq	_perror
	movl	$1, %edi
	callq	_exit
	.cfi_endproc
                                        ## -- End function
	.globl	_queue_push                     ## -- Begin function queue_push
	.p2align	4, 0x90
_queue_push:                            ## @queue_push
	.cfi_startproc
## %bb.0:
	pushq	%r14
	.cfi_def_cfa_offset 16
	pushq	%rbx
	.cfi_def_cfa_offset 24
	pushq	%rax
	.cfi_def_cfa_offset 32
	.cfi_offset %rbx, -24
	.cfi_offset %r14, -16
	movq	%rsi, %rbx
	movq	%rdi, %r14
	leaq	_mutex(%rip), %rdi
	callq	_pthread_mutex_lock
	testl	%eax, %eax
	jne	LBB1_1
## %bb.3:
	movl	$1, %ecx
	lock		xaddq	%rcx, _count(%rip)
	cmpq	_QUEUE_SIZE(%rip), %rcx
	jae	LBB1_6
## %bb.4:
	movq	_queue(%rip), %rax
	testq	%rcx, %rcx
	je	LBB1_5
	.p2align	4, 0x90
LBB1_8:                                 ## =>This Inner Loop Header: Depth=1
	leaq	-1(%rcx), %rsi
	movq	%rsi, %rdx
	shrq	%rdx
	movq	%rdx, %rdi
	shlq	$4, %rdi
	cmpq	%rbx, 8(%rax,%rdi)
	jle	LBB1_9
## %bb.7:                               ##   in Loop: Header=BB1_8 Depth=1
	shlq	$4, %rcx
	movups	(%rax,%rdi), %xmm0
	movups	%xmm0, (%rax,%rcx)
	movq	%rdx, %rcx
	cmpq	$2, %rsi
	jae	LBB1_8
	jmp	LBB1_10
LBB1_5:
	xorl	%edx, %edx
	jmp	LBB1_10
LBB1_9:
	movq	%rcx, %rdx
LBB1_10:
	shlq	$4, %rdx
	movq	%r14, (%rax,%rdx)
	movq	%rbx, 8(%rax,%rdx)
	leaq	_cond(%rip), %rdi
	callq	_pthread_cond_signal
	testl	%eax, %eax
	jne	LBB1_11
## %bb.12:
	leaq	_mutex(%rip), %rdi
	callq	_pthread_mutex_unlock
	testl	%eax, %eax
	jne	LBB1_13
## %bb.14:
	addq	$8, %rsp
	popq	%rbx
	popq	%r14
	retq
LBB1_1:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.1(%rip), %rsi
	jmp	LBB1_2
LBB1_6:
	lock		decq	_count(%rip)
	movq	___stderrp@GOTPCREL(%rip), %rax
	movq	(%rax), %rcx
	leaq	L_.str.2(%rip), %rdi
	movl	$18, %esi
	movl	$1, %edx
	callq	_fwrite
	movl	$1, %edi
	callq	_exit
LBB1_11:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.3(%rip), %rsi
	jmp	LBB1_2
LBB1_13:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.4(%rip), %rsi
LBB1_2:
	movl	%eax, %edx
	xorl	%eax, %eax
	callq	_fprintf
	movl	$1, %edi
	callq	_exit
	.cfi_endproc
                                        ## -- End function
	.globl	_queue_pop                      ## -- Begin function queue_pop
	.p2align	4, 0x90
_queue_pop:                             ## @queue_pop
	.cfi_startproc
## %bb.0:
	pushq	%r14
	.cfi_def_cfa_offset 16
	pushq	%rbx
	.cfi_def_cfa_offset 24
	pushq	%rax
	.cfi_def_cfa_offset 32
	.cfi_offset %rbx, -24
	.cfi_offset %r14, -16
	leaq	_mutex(%rip), %rdi
	callq	_pthread_mutex_lock
	testl	%eax, %eax
	jne	LBB2_5
## %bb.1:
	leaq	_cond(%rip), %r14
	leaq	_mutex(%rip), %rbx
	.p2align	4, 0x90
LBB2_2:                                 ## =>This Inner Loop Header: Depth=1
	movq	_count(%rip), %rax
	testq	%rax, %rax
	jne	LBB2_7
## %bb.3:                               ##   in Loop: Header=BB2_2 Depth=1
	movq	%r14, %rdi
	movq	%rbx, %rsi
	callq	_pthread_cond_wait
	testl	%eax, %eax
	je	LBB2_2
## %bb.4:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.5(%rip), %rsi
LBB2_6:
	movl	%eax, %edx
	xorl	%eax, %eax
	callq	_fprintf
	movl	$1, %edi
	callq	_exit
LBB2_7:
	lock		decq	_count(%rip)
	movq	_queue(%rip), %rax
	movq	(%rax), %r14
	movq	_count(%rip), %rax
	testq	%rax, %rax
	je	LBB2_19
## %bb.8:
	movq	_queue(%rip), %rax
	movq	_count(%rip), %rcx
	shlq	$4, %rcx
	movq	(%rax,%rcx), %r8
	movq	8(%rax,%rcx), %r9
	movq	_count(%rip), %rax
	cmpq	$2, %rax
	jb	LBB2_9
## %bb.10:
	movl	$1, %edi
	xorl	%eax, %eax
	xorl	%esi, %esi
	.p2align	4, 0x90
LBB2_11:                                ## =>This Inner Loop Header: Depth=1
	movq	%rax, %rdx
	addq	$2, %rdx
	movq	_count(%rip), %rcx
	movq	_queue(%rip), %rax
	cmpq	%rcx, %rdx
	jae	LBB2_12
## %bb.13:                              ##   in Loop: Header=BB2_11 Depth=1
	movq	%rdx, %rcx
	shlq	$4, %rcx
	movq	8(%rax,%rcx), %rbx
	movq	%rdi, %rcx
	shlq	$4, %rcx
	movq	8(%rax,%rcx), %rcx
	cmpq	%rcx, %rbx
	jge	LBB2_14
## %bb.15:                              ##   in Loop: Header=BB2_11 Depth=1
	cmpq	%r9, %rbx
	jl	LBB2_17
	jmp	LBB2_16
	.p2align	4, 0x90
LBB2_12:                                ##   in Loop: Header=BB2_11 Depth=1
	movq	%rdi, %rcx
	shlq	$4, %rcx
	movq	8(%rax,%rcx), %rcx
LBB2_14:                                ##   in Loop: Header=BB2_11 Depth=1
	movq	%rcx, %rbx
	movq	%rdi, %rdx
	cmpq	%r9, %rbx
	jge	LBB2_16
LBB2_17:                                ##   in Loop: Header=BB2_11 Depth=1
	movq	%rdx, %rcx
	shlq	$4, %rcx
	shlq	$4, %rsi
	movups	(%rax,%rcx), %xmm0
	movups	%xmm0, (%rax,%rsi)
	leaq	(%rdx,%rdx), %rax
	leaq	(%rdx,%rdx), %rdi
	incq	%rdi
	movq	_count(%rip), %rcx
	movq	%rdx, %rsi
	cmpq	%rcx, %rdi
	jb	LBB2_11
	jmp	LBB2_18
LBB2_9:
	xorl	%edx, %edx
	jmp	LBB2_18
LBB2_16:
	movq	%rsi, %rdx
LBB2_18:
	movq	_queue(%rip), %rax
	shlq	$4, %rdx
	movq	%r8, (%rax,%rdx)
	movq	%r9, 8(%rax,%rdx)
LBB2_19:
	leaq	_mutex(%rip), %rdi
	callq	_pthread_mutex_unlock
	testl	%eax, %eax
	jne	LBB2_20
## %bb.21:
	movq	%r14, %rax
	addq	$8, %rsp
	popq	%rbx
	popq	%r14
	retq
LBB2_5:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.1(%rip), %rsi
	jmp	LBB2_6
LBB2_20:
	movq	___stderrp@GOTPCREL(%rip), %rcx
	movq	(%rcx), %rdi
	leaq	L_.str.4(%rip), %rsi
	jmp	LBB2_6
	.cfi_endproc
                                        ## -- End function
.zerofill __DATA,__bss,_QUEUE_SIZE,8,3  ## @QUEUE_SIZE
.zerofill __DATA,__bss,_queue,8,3       ## @queue
	.section	__TEXT,__cstring,cstring_literals
L_.str:                                 ## @.str
	.asciz	"malloc"

	.section	__DATA,__data
	.p2align	3                               ## @mutex
_mutex:
	.quad	850045863                       ## 0x32aaaba7
	.space	56

	.section	__TEXT,__cstring,cstring_literals
L_.str.1:                               ## @.str.1
	.asciz	"pthread_mutex_lock failed with code %d\n"

.zerofill __DATA,__bss,_count,8,3       ## @count
L_.str.2:                               ## @.str.2
	.asciz	"job queue is full\n"

	.section	__DATA,__data
	.p2align	3                               ## @cond
_cond:
	.quad	1018212795                      ## 0x3cb0b1bb
	.space	40

	.section	__TEXT,__cstring,cstring_literals
L_.str.3:                               ## @.str.3
	.asciz	"pthread_cond_signal failed with code %d\n"

L_.str.4:                               ## @.str.4
	.asciz	"pthread_mutex_unlock failed with code %d\n"

L_.str.5:                               ## @.str.5
	.asciz	"pthread_cond_wait failed with code %d\n"

.subsections_via_symbols
