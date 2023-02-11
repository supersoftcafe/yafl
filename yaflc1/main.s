	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 11, 0
	.globl	_swap_context                   ## -- Begin function swap_context
	.p2align	4, 0x90
_swap_context:                          ## @swap_context
	.cfi_startproc
## %bb.0:
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset %rbp, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register %rbp
	movq	%rdi, -8(%rbp)
	movq	%rsi, -16(%rbp)
	movq	%rdx, -24(%rbp)
	movq	-16(%rbp), %rax
	movq	-24(%rbp), %rcx
	## InlineAsm Start
	movq	(%rsp), %r8
	movq	%r8, (%rax)
	leaq	8(%rsp), %r8
	movq	%r8, 8(%rax)
	movq	%rbx, 16(%rax)
	movq	%rbp, 24(%rax)
	movq	%r12, 32(%rax)
	movq	%r13, 40(%rax)
	movq	%r14, 48(%rax)
	movq	%r15, 56(%rax)
	movq	(%rcx), %r8
	movq	8(%rcx), %rsp
	movq	16(%rcx), %rbx
	movq	24(%rcx), %rbp
	movq	32(%rcx), %r12
	movq	40(%rcx), %r13
	movq	48(%rcx), %r14
	movq	56(%rcx), %r15
	pushq	%r8
	## InlineAsm End
	popq	%rbp
	retq
	.cfi_endproc
                                        ## -- End function
	.globl	_crummy_func                    ## -- Begin function crummy_func
	.p2align	4, 0x90
_crummy_func:                           ## @crummy_func
	.cfi_startproc
## %bb.0:
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset %rbp, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register %rbp
	subq	$16, %rsp
	movq	%rdi, -8(%rbp)
	movq	-8(%rbp), %rsi
	leaq	L_.str(%rip), %rdi
	movb	$0, %al
	callq	_printf
	xorl	%eax, %eax
	movl	%eax, %edi
	leaq	_target_context(%rip), %rsi
	leaq	_origin_context(%rip), %rdx
	callq	_swap_context
	addq	$16, %rsp
	popq	%rbp
	retq
	.cfi_endproc
                                        ## -- End function
	.globl	_main                           ## -- Begin function main
	.p2align	4, 0x90
_main:                                  ## @main
	.cfi_startproc
## %bb.0:
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset %rbp, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register %rbp
	subq	$16, %rsp
	movl	$0, -4(%rbp)
	movl	$65536, %edi                    ## imm = 0x10000
	callq	_malloc
	movq	%rax, -16(%rbp)
	movq	-16(%rbp), %rax
	andq	$-16, %rax
	subq	$128, %rax
	movq	%rax, _target_context+8(%rip)
	leaq	_crummy_func(%rip), %rax
	movq	%rax, _target_context(%rip)
	leaq	L_.str.1(%rip), %rdi
	movb	$0, %al
	callq	_printf
	leaq	L_.str.2(%rip), %rdi
	leaq	_origin_context(%rip), %rsi
	leaq	_target_context(%rip), %rdx
	callq	_swap_context
	leaq	L_.str.3(%rip), %rdi
	movb	$0, %al
	callq	_printf
	xorl	%eax, %eax
	addq	$16, %rsp
	popq	%rbp
	retq
	.cfi_endproc
                                        ## -- End function
	.section	__TEXT,__cstring,cstring_literals
L_.str:                                 ## @.str
	.asciz	"Message is: %s\n"

	.globl	_target_context                 ## @target_context
.zerofill __DATA,__common,_target_context,64,3
	.globl	_origin_context                 ## @origin_context
.zerofill __DATA,__common,_origin_context,64,3
L_.str.1:                               ## @.str.1
	.asciz	"Entering new context\n"

L_.str.2:                               ## @.str.2
	.asciz	"Hello world!"

L_.str.3:                               ## @.str.3
	.asciz	"Re-entered old context\n"

.subsections_via_symbols
