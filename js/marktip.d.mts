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
    _mt_equals(left: number, right: number): number;
    _mt_document_free(document: number): void;
    _mt_schema_free(schema: number): void;
    _mt_version(): void;
    _mt_result_ptr(): number;
    _mt_result_len(): number;
    _mt_error_ptr(): number;
    _mt_error_len(): number;
};

export default function createModule(): Promise<WasmModule>;
