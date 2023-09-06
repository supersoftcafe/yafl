package com.supersoftcafe.yafl.models.llir

data class CgClassInfo(val name: String) {
    val vtableDataName = "@\"vtable\$$name\""   // VTable declaration of type 'vtableTypeName'
    val deleteFuncName = "@\"release\$$name\""   // Function to release all references and then delete the underlying object
    val objectTypeName = "%\"typeof.object\$$name\""    // Typedef used for access to object fields and bitcast
    val vtableTypeName = "%\"typeof.vtable\$$name\""    // Typedef used for vtable declaration and bitcast
}
