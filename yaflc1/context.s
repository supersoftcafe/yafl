	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 11, 0
	.globl	_swap_context                   ## -- Begin function swap_context
	.p2align	4, 0x90
_swap_context:                          ## @swap_context
	.cfi_startproc
## %bb.0:
	## InlineAsm Start
	movq	(%rsp), %r8
	movq	%r8, (%rsi)
	leaq	8(%rsp), %r8
	movq	%r8, 8(%rsi)
	movq	%rbx, 16(%rsi)
	movq	%rbp, 24(%rsi)
	movq	%r12, 32(%rsi)
	movq	%r13, 40(%rsi)
	movq	%r14, 48(%rsi)
	movq	%r15, 56(%rsi)
	movq	(%rdx), %r8
	movq	8(%rdx), %rsp
	movq	16(%rdx), %rbx
	movq	24(%rdx), %rbp
	movq	32(%rdx), %r12
	movq	40(%rdx), %r13
	movq	48(%rdx), %r14
	movq	56(%rdx), %r15
	pushq	%r8
	## InlineAsm End
	retq
	.cfi_endproc
                                        ## -- End function
.subsections_via_symbols
