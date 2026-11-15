import createModule from "../build-wasm/marktip.mjs";

type WasmModule = {
    HEAPU8: Uint8Array;
    _malloc(size: number): number;
    _free(pointer: number): void;
    _mt_schema_new(pointer: number, length: number): number;
    _mt_from_markdown(pointer: number, length: number, options: number, optionsLength: number,
                      schema: number): number;
    _mt_from_dict(pointer: number, length: number, options: number, optionsLength: number,
                  schema: number, base: number): number;
    _mt_load(pointer: number, length: number, schema: number): number;
    _mt_to_dict(document: number): void;
    _mt_dump(document: number): void;
    _mt_to_markdown(document: number, canonical: number): void;
    _mt_document_free(document: number): void;
    _mt_schema_free(schema: number): void;
    _mt_version(): void;
    _mt_result_ptr(): number;
    _mt_result_len(): number;
    _mt_error_ptr(): number;
    _mt_error_len(): number;
};

type ErrorFields = {
    code?: string;
    path?: string;
    detail?: string;
    field?: string;
    type?: string;
    kind?: string;
};

type Options = Record<string, unknown>;
type Buffer = { pointer: number; length: number };

let wasm: WasmModule | undefined;
let initialization: Promise<void> | undefined;
export let version = "";

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { ignoreBOM: true });
const schemas = new WeakMap<Schema, number>();
const documents = new WeakMap<Document, number>();
const schemaFinalizer = new FinalizationRegistry<number>((handle) => { wasm!._mt_schema_free(handle); });
const documentFinalizer = new FinalizationRegistry<number>((handle) => { wasm!._mt_document_free(handle); });

export class MarktipError extends Error {
    code: string;
    path: string;
    detail: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message);
        this.name = new.target.name;
        this.code = fields.code ?? "";
        this.path = fields.path ?? "";
        this.detail = fields.detail ?? message;
    }
}

export class UnknownTypeError extends MarktipError {
    type: string;
    kind: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message, fields);
        this.type = fields.type ?? "";
        this.kind = fields.kind ?? "";
    }
}

export class InvalidNodeError extends MarktipError {
    field: string;

    constructor(message: string, fields: ErrorFields = {}) {
        super(message, fields);
        this.field = fields.field ?? "";
    }
}

export class ParseError extends MarktipError {}

function runtime(): WasmModule {
    if (!wasm) {
        throw new Error("Call await init() before using marktip.");
    }
    return wasm;
}

function decode(module: WasmModule, pointer: number, length: number): string {
    return decoder.decode(module.HEAPU8.subarray(pointer, pointer + length));
}

function checkError(module: WasmModule): void {
    const length = module._mt_error_len();
    if (length === 0) return;
    const error = JSON.parse(decode(module, module._mt_error_ptr(), length));
    switch (error.name) {
        case "UnknownTypeError": throw new UnknownTypeError(error.message, error);
        case "InvalidNodeError": throw new InvalidNodeError(error.message, error);
        case "ParseError": throw new ParseError(error.message, error);
        case "MarktipError": throw new MarktipError(error.message, error);
        case "TypeError": throw new TypeError(error.message);
        case "RangeError": throw new RangeError(error.message);
        default: throw new Error(error.message);
    }
}

function result(module: WasmModule): string {
    checkError(module);
    return decode(module, module._mt_result_ptr(), module._mt_result_len());
}

function withStrings<T>(values: string[], call: (module: WasmModule, buffers: Buffer[]) => T): T {
    const module = runtime();
    const buffers: Buffer[] = [];
    try {
        for (const value of values) {
            const bytes = encoder.encode(value);
            const pointer = module._malloc(Math.max(1, bytes.length));
            buffers.push({ pointer, length: bytes.length });
            module.HEAPU8.set(bytes, pointer);
        }
        const output = call(module, buffers);
        checkError(module);
        return output;
    } finally {
        for (const buffer of buffers) module._free(buffer.pointer);
    }
}

function json(value: unknown): string {
    const text = JSON.stringify(value);
    if (text === undefined) throw new TypeError("value must be JSON-serializable");
    return text;
}

function optionsObject(value: unknown, name: string): Options {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new TypeError(`${name} must be an object`);
    }
    return value as Options;
}

function optionNames(options: Options, allowed: string[]): void {
    for (const name of Object.keys(options)) {
        if (!allowed.includes(name)) throw new TypeError(`unknown option '${name}'`);
    }
}

function schemaHandle(value: unknown): number {
    if (value === undefined || value === null) return 0;
    if (!(value instanceof Schema)) throw new TypeError("schema must be a Schema or null");
    const handle = schemas.get(value)!;
    if (handle === 0) throw new Error("Schema has been freed");
    return handle;
}

function documentHandle(value: unknown): number {
    if (!(value instanceof Document)) throw new TypeError("base must be a Document or null");
    const handle = documents.get(value)!;
    if (handle === 0) throw new Error("Document has been freed");
    return handle;
}

function documentFromHandle(handle: number): Document {
    const document = Object.create(Document.prototype) as Document;
    documents.set(document, handle);
    documentFinalizer.register(document, handle, document);
    return document;
}

export function init(): Promise<void> {
    if (!initialization) {
        initialization = createModule().then((module: WasmModule) => {
            module._mt_version();
            version = result(module);
            wasm = module;
        });
    }
    return initialization;
}

export class Schema {
    constructor(declaration: Options = {}) {
        runtime();
        const { marks = [], nodes = [], coreAttrs = {}, blockImage = false } = (
            optionsObject(declaration, "schema declaration")
        );
        const text = json({ marks, nodes, core_attrs: coreAttrs ?? {}, block_image: blockImage });
        const handle = withStrings([text], (module, [input]) => module._mt_schema_new(input.pointer, input.length));
        schemas.set(this, handle);
        schemaFinalizer.register(this, handle, this);
    }

    free(): void {
        const handle = schemas.get(this)!;
        if (handle === 0) return;
        const module = runtime();
        module._mt_schema_free(handle);
        checkError(module);
        schemas.set(this, 0);
        schemaFinalizer.unregister(this);
    }
}

export class Document {
    private constructor() {}

    toDict(): unknown {
        const module = runtime();
        module._mt_to_dict(documentHandle(this));
        return JSON.parse(result(module));
    }

    dump(): unknown {
        const module = runtime();
        module._mt_dump(documentHandle(this));
        return JSON.parse(result(module));
    }

    toMarkdown(options: Options = {}): string {
        const settings = optionsObject(options, "options");
        optionNames(settings, ["canonical"]);
        const { canonical = false } = settings;
        if (typeof canonical !== "boolean") throw new TypeError("canonical must be a bool");
        const module = runtime();
        module._mt_to_markdown(documentHandle(this), canonical ? 1 : 0);
        return result(module);
    }

    free(): void {
        const handle = documents.get(this)!;
        if (handle === 0) return;
        const module = runtime();
        module._mt_document_free(handle);
        checkError(module);
        documents.set(this, 0);
        documentFinalizer.unregister(this);
    }
}

export function fromMarkdown(markdown: string, options: Options = {}): Document {
    runtime();
    if (typeof markdown !== "string") throw new TypeError("fromMarkdown() expects a string");
    const { schema, ...wire } = optionsObject(options, "options");
    const selected = schemaHandle(schema);
    const handle = withStrings([markdown, json(wire)], (module, [input, settings]) => (
        module._mt_from_markdown(input.pointer, input.length, settings.pointer, settings.length, selected)
    ));
    return documentFromHandle(handle);
}

export function fromDict(value: unknown, options: Options = {}): Document {
    runtime();
    const { schema, base, ...wire } = optionsObject(options, "options");
    const selected = schemaHandle(schema);
    const inherited = base === undefined || base === null ? 0 : documentHandle(base);
    const handle = withStrings([json(value), json(wire)], (module, [input, settings]) => (
        module._mt_from_dict(input.pointer, input.length, settings.pointer, settings.length, selected, inherited)
    ));
    return documentFromHandle(handle);
}

export function load(value: unknown, options: Options = {}): Document {
    runtime();
    const settings = optionsObject(options, "options");
    optionNames(settings, ["schema"]);
    const selected = schemaHandle(settings.schema);
    const handle = withStrings([json(value)], (module, [input]) => (
        module._mt_load(input.pointer, input.length, selected)
    ));
    return documentFromHandle(handle);
}
