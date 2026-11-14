#pragma once

#if defined(_MSC_VER)
#define MARKTIP_NOINLINE __declspec(noinline)
#else
#define MARKTIP_NOINLINE __attribute__((noinline))
#endif
