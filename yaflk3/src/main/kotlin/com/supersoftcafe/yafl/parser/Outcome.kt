package com.supersoftcafe.yafl.parser

sealed class Outcome<TValue> {
    data class Success<TValue>(val value: TValue) : Outcome<TValue>()
    data class Failure<TValue>(val error: String) : Outcome<TValue>()
}