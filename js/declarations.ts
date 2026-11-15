export type AttrValue = string | number | boolean | readonly number[];

export interface Attr {
    type: "str" | "int" | "bool" | "IntList";
    required?: boolean;
    choices?: readonly AttrValue[] | null;
    default?: AttrValue | null;
    uri?: string | null;
}

export interface MarkSpec {
    name: string;
    tag?: string | null;
    attrs?: Record<string, Attr>;
    excludes?: readonly string[] | string | null;
}

export interface NodeSpec {
    name: string;
    kind: string;
    content?: string | null;
    group?: string | null;
    tag?: string | null;
    attrs?: Record<string, Attr>;
    implicit?: boolean;
    fence?: string | null;
    math?: string | null;
    body?: string | null;
}

export type CoreAttrs = Record<string, Record<string, Attr>>;

export interface SchemaDict {
    marks: readonly MarkSpec[];
    nodes?: readonly NodeSpec[];
    core_attrs?: CoreAttrs;
    block_image?: boolean;
}

export function normalizeAttrs(attrs: Record<string, Attr>): Record<string, Attr> {
    return Object.fromEntries(Object.entries(attrs).map(([name, attr]) => [name, {
        type: attr.type,
        required: attr.required ?? false,
        choices: attr.choices == null ? null : [...attr.choices],
        default: attr.default ?? null,
        uri: attr.uri ?? null,
    }]));
}

export function normalizeCoreAttrs(coreAttrs: CoreAttrs): CoreAttrs {
    return Object.fromEntries(Object.entries(coreAttrs).map(([owner, attrs]) => [owner, normalizeAttrs(attrs)]));
}

export function normalizeMark(mark: MarkSpec): MarkSpec {
    return {
        name: mark.name,
        tag: mark.tag ?? null,
        attrs: normalizeAttrs(mark.attrs ?? {}),
        excludes: Array.isArray(mark.excludes) ? [...mark.excludes] : mark.excludes ?? null,
    };
}

export function normalizeNode(node: NodeSpec): NodeSpec {
    return {
        name: node.name,
        kind: node.kind,
        content: node.content ?? null,
        group: node.group ?? null,
        tag: node.tag ?? null,
        attrs: normalizeAttrs(node.attrs ?? {}),
        implicit: node.implicit ?? false,
        fence: node.fence ?? null,
        math: node.math ?? null,
        body: node.body ?? null,
    };
}

export function declarationToDict(marks: readonly MarkSpec[], nodes: readonly NodeSpec[],
                                  coreAttrs: CoreAttrs, blockImage: boolean): SchemaDict {
    const wire = JSON.parse(JSON.stringify({ marks, nodes, core_attrs: coreAttrs })) as Required<SchemaDict>;
    const declaration: SchemaDict = { marks: wire.marks.map(normalizeMark) };
    if (wire.nodes.length) declaration.nodes = wire.nodes.map(normalizeNode);
    if (Object.keys(wire.core_attrs).length) {
        declaration.core_attrs = normalizeCoreAttrs(wire.core_attrs);
    }
    if (blockImage) declaration.block_image = true;
    return declaration;
}
