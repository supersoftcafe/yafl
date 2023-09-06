package com.supersoftcafe.yafl.models.ast

import com.supersoftcafe.yafl.utils.Namer

sealed class Guidance {
    data class Exclude(val name: String, val id: Namer) : Guidance()
}
