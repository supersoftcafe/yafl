	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 11, 0
	.globl	_log_error                      ## -- Begin function log_error
	.p2align	4, 0x90
_log_error:                             ## @log_error
	.cfi_startproc
## %bb.0:
	subq	$216, %rsp
	.cfi_def_cfa_offset 224
	movq	%rdi, %r10
	movq	%rsi, 8(%rsp)
	movq	%rdx, 16(%rsp)
	movq	%rcx, 24(%rsp)
	movq	%r8, 32(%rsp)
	movq	%r9, 40(%rsp)
	testb	%al, %al
	je	LBB0_4
## %bb.3:
	movaps	%xmm0, 48(%rsp)
	movaps	%xmm1, 64(%rsp)
	movaps	%xmm2, 80(%rsp)
	movaps	%xmm3, 96(%rsp)
	movaps	%xmm4, 112(%rsp)
	movaps	%xmm5, 128(%rsp)
	movaps	%xmm6, 144(%rsp)
	movaps	%xmm7, 160(%rsp)
LBB0_4:
	movq	___stack_chk_guard@GOTPCREL(%rip), %rax
	movq	(%rax), %rax
	movq	%rax, 208(%rsp)
	movq	%rsp, %rax
	movq	%rax, 192(%rsp)
	leaq	224(%rsp), %rax
	movq	%rax, 184(%rsp)
	movabsq	$206158430216, %rax             ## imm = 0x3000000008
	movq	%rax, 176(%rsp)
	movq	___stderrp@GOTPCREL(%rip), %rax
	movq	(%rax), %rdi
	leaq	176(%rsp), %rdx
	movq	%r10, %rsi
	callq	_vfprintf
	movq	___stack_chk_guard@GOTPCREL(%rip), %rax
	movq	(%rax), %rax
	cmpq	208(%rsp), %rax
	jne	LBB0_2
## %bb.1:
	addq	$216, %rsp
	retq
LBB0_2:
	callq	___stack_chk_fail
	.cfi_endproc
                                        ## -- End function
	.globl	_log_error_and_exit             ## -- Begin function log_error_and_exit
	.p2align	4, 0x90
_log_error_and_exit:                    ## @log_error_and_exit
	.cfi_startproc
## %bb.0:
	pushq	%rbx
	.cfi_def_cfa_offset 16
	subq	$208, %rsp
	.cfi_def_cfa_offset 224
	.cfi_offset %rbx, -16
	movq	%rdi, %rbx
	movq	%rsi, 40(%rsp)
	movq	%rdx, 48(%rsp)
	movq	%rcx, 56(%rsp)
	movq	%r8, 64(%rsp)
	movq	%r9, 72(%rsp)
	testb	%al, %al
	je	LBB1_2
## %bb.1:
	movaps	%xmm0, 80(%rsp)
	movaps	%xmm1, 96(%rsp)
	movaps	%xmm2, 112(%rsp)
	movaps	%xmm3, 128(%rsp)
	movaps	%xmm4, 144(%rsp)
	movaps	%xmm5, 160(%rsp)
	movaps	%xmm6, 176(%rsp)
	movaps	%xmm7, 192(%rsp)
LBB1_2:
	callq	___error
	movl	(%rax), %esi
	leaq	L_.str(%rip), %rdi
	xorl	%eax, %eax
	callq	_log_error
	leaq	32(%rsp), %rax
	movq	%rax, 16(%rsp)
	leaq	224(%rsp), %rax
	movq	%rax, 8(%rsp)
	movabsq	$206158430216, %rax             ## imm = 0x3000000008
	movq	%rax, (%rsp)
	movq	___stderrp@GOTPCREL(%rip), %rax
	movq	(%rax), %rdi
	movq	%rsp, %rdx
	movq	%rbx, %rsi
	callq	_vfprintf
	movl	$1, %edi
	callq	_exit
	.cfi_endproc
                                        ## -- End function
	.section	__TEXT,__cstring,cstring_literals
L_.str:                                 ## @.str
	.asciz	"errno %d\n"

.subsections_via_symbols
