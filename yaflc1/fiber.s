	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 11, 0
	.globl	_fiber_create                   ## -- Begin function fiber_create
	.p2align	4, 0x90
_fiber_create:                          ## @fiber_create
	.cfi_startproc
## %bb.0:
	pushq	%rbx
	.cfi_def_cfa_offset 16
	.cfi_offset %rbx, -16
	movq	%rdi, %rbx
	movq	$65536, 24(%rdi)                ## imm = 0x10000
	movl	$65536, %edi                    ## imm = 0x10000
	callq	_malloc
	movq	%rax, 16(%rbx)
	movq	$0, (%rbx)
	addq	$-128, %rax
	andq	$-16, %rax
	movq	%rax, 8(%rbx)
	popq	%rbx
	retq
	.cfi_endproc
                                        ## -- End function
	.globl	_fiber_init                     ## -- Begin function fiber_init
	.p2align	4, 0x90
_fiber_init:                            ## @fiber_init
	.cfi_startproc
## %bb.0:
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	%rsi, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	%rdx, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	movq	8(%rdi), %rax
	leaq	-8(%rax), %rcx
	movq	%rcx, 8(%rdi)
	movq	$0, -8(%rax)
	retq
	.cfi_endproc
                                        ## -- End function
	.globl	_fiber_enter                    ## -- Begin function fiber_enter
	.p2align	4, 0x90
_fiber_enter:                           ## @fiber_enter
	.cfi_startproc
## %bb.0:
	movq	(%rdi), %rax
	movq	8(%rdi), %rsi
	movq	%rax, %rdi
	jmp	_fiber_swap_context             ## TAILCALL
	.cfi_endproc
                                        ## -- End function
	.globl	_fiber_yield                    ## -- Begin function fiber_yield
	.p2align	4, 0x90
_fiber_yield:                           ## @fiber_yield
	.cfi_startproc
## %bb.0:
	movq	(%rdi), %rsi
	movq	8(%rdi), %rdi
	jmp	_fiber_swap_context             ## TAILCALL
	.cfi_endproc
                                        ## -- End function
	.globl	_fiber_destroy                  ## -- Begin function fiber_destroy
	.p2align	4, 0x90
_fiber_destroy:                         ## @fiber_destroy
	.cfi_startproc
## %bb.0:
	movq	16(%rdi), %rdi
	jmp	_free                           ## TAILCALL
	.cfi_endproc
                                        ## -- End function
.subsections_via_symbols
