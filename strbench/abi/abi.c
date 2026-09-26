typedef unsigned int uint32_t; typedef unsigned char uint8_t;
typedef struct { void* head; uint32_t meta; uint8_t tail[4]; } s16;   /* 64-bit: 16 B; 32-bit: 12 B */
typedef struct { void* head; uint32_t meta; uint8_t tail[8]; } s16_32; /* 32-bit: 16 B */
typedef struct { void* head; uint32_t meta; } s8_32;                    /* 32-bit: 8 B */
extern s16 g16(s16 a); extern s16_32 g16b(s16_32 a); extern s8_32 g8(s8_32 a);
s16    f16(s16 a)     { return g16(a); }
s16_32 f16b(s16_32 a) { return g16b(a); }
s8_32  f8(s8_32 a)    { return g8(a); }
