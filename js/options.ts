export function optionsObject(value: unknown, name: string): Record<string, unknown> {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new TypeError(`${name} must be an object`);
    }
    return value as Record<string, unknown>;
}

export function optionNames(options: Record<string, unknown>, allowed: readonly string[]): void {
    for (const name of Object.keys(options)) {
        if (!allowed.includes(name)) throw new TypeError(`unknown option '${name}'`);
    }
}
