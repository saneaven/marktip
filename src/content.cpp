#include "content.h"

#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>
#include <unordered_set>
#include <utility>

namespace marktip {
namespace {

constexpr std::size_t kCompilationBudget = 4096;

class Budget {
public:
    void charge() {
        if (used_ == kCompilationBudget) {
            throw std::invalid_argument("content expression exceeds compilation budget");
        }
        ++used_;
    }

private:
    std::size_t used_ = 0;
};

enum class ExprKind { Name, Sequence, Choice, Repeat };

struct Expr {
    ExprKind kind;
    std::size_t left = 0;
    std::size_t right = 0;
    std::vector<std::size_t> types = {};
    std::size_t min = 0;
    std::optional<std::size_t> max = std::nullopt;
};

bool word_char(char value) {
    return (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') ||
           (value >= '0' && value <= '9') || value == '_';
}

std::size_t space_length(std::string_view value) {
    char first = value.front();
    if (first == ' ' || first == '\t' || first == '\r' || first == '\n' || first == '\f' || first == '\v') {
        return 1;
    }
    // ProseMirror tokenization uses JavaScript \s, which also skips Unicode separators and line terminators.
    constexpr std::string_view unicode[] = {
        u8"\u00A0", u8"\u1680", u8"\u2000", u8"\u2001", u8"\u2002", u8"\u2003", u8"\u2004",
        u8"\u2005", u8"\u2006", u8"\u2007", u8"\u2008", u8"\u2009", u8"\u200A", u8"\u2028",
        u8"\u2029", u8"\u202F", u8"\u205F", u8"\u3000", u8"\uFEFF",
    };
    for (std::string_view whitespace : unicode) {
        if (value.substr(0, whitespace.size()) == whitespace) {
            return whitespace.size();
        }
    }
    return 0;
}

[[noreturn]] void invalid_expression(std::string_view expression, const char* reason) {
    throw std::invalid_argument(std::string(reason) + " in content expression '" + std::string(expression) + "'");
}

class ExpressionParser {
public:
    ExpressionParser(std::string_view expression, const std::vector<ContentType>& types, Budget& budget)
        : expression_(expression), types_(types), budget_(budget) {}

    std::optional<std::size_t> parse() {
        bool expect_atom = true;
        while (skip_space(), position_ != expression_.size()) {
            char token = expression_[position_];
            if (word_char(token) || token == '(') {
                if (!expect_atom) {
                    push_operator('.');
                }
                if (token == '(') {
                    budget_.charge();
                    operators_.push_back('(');
                    ++position_;
                    expect_atom = true;
                } else {
                    std::size_t begin = position_++;
                    while (position_ != expression_.size() && word_char(expression_[position_])) {
                        ++position_;
                    }
                    Expr expr {ExprKind::Name};
                    expr.types = resolve(expression_.substr(begin, position_ - begin));
                    values_.push_back(append(std::move(expr)));
                    expect_atom = false;
                }
            } else if (token == ')') {
                if (expect_atom) {
                    invalid_expression(expression_, "unexpected closing parenthesis");
                }
                while (!operators_.empty() && operators_.back() != '(') {
                    reduce();
                }
                if (operators_.empty()) {
                    invalid_expression(expression_, "unmatched closing parenthesis");
                }
                operators_.pop_back();
                ++position_;
            } else if (token == '|') {
                if (expect_atom) {
                    invalid_expression(expression_, "missing alternative");
                }
                push_operator('|');
                ++position_;
                expect_atom = true;
            } else if (token == '*' || token == '+' || token == '?' || token == '{') {
                if (expect_atom) {
                    invalid_expression(expression_, "repetition has no expression");
                }
                Expr expr {ExprKind::Repeat};
                expr.left = values_.back();
                ++position_;
                if (token == '?') {
                    expr.max = 1;
                } else if (token == '+') {
                    expr.min = 1;
                } else if (token == '{') {
                    expr.min = number();
                    expr.max = expr.min;
                    skip_space();
                    if (position_ != expression_.size() && expression_[position_] == ',') {
                        ++position_;
                        skip_space();
                        expr.max = position_ != expression_.size() && expression_[position_] == '}'
                                       ? std::nullopt : std::optional<std::size_t>(number());
                    }
                    skip_space();
                    if (position_ == expression_.size() || expression_[position_] != '}') {
                        invalid_expression(expression_, "unclosed repetition range");
                    }
                    ++position_;
                }
                values_.back() = append(std::move(expr));
            } else {
                invalid_expression(expression_, "unexpected token");
            }
        }
        if (expect_atom && !values_.empty()) {
            invalid_expression(expression_, "missing expression");
        }
        while (!operators_.empty()) {
            if (operators_.back() == '(') {
                invalid_expression(expression_, "unclosed parenthesis");
            }
            reduce();
        }
        return values_.empty() ? std::nullopt : std::optional<std::size_t>(values_.back());
    }

    const std::vector<Expr>& expressions() const { return expressions_; }
    std::optional<bool> inline_content() const { return inline_content_; }

private:
    std::string_view expression_;
    const std::vector<ContentType>& types_;
    Budget& budget_;
    std::size_t position_ = 0;
    std::vector<Expr> expressions_;
    std::vector<std::size_t> values_;
    std::vector<char> operators_;
    std::optional<bool> inline_content_;

    void skip_space() {
        while (position_ != expression_.size()) {
            std::size_t length = space_length(expression_.substr(position_));
            if (length == 0) {
                break;
            }
            position_ += length;
        }
    }

    std::size_t append(Expr expr) {
        budget_.charge();
        expressions_.push_back(std::move(expr));
        return expressions_.size() - 1;
    }

    std::vector<std::size_t> resolve(std::string_view name) {
        std::vector<std::size_t> matches;
        for (std::size_t i = 0; i < types_.size(); ++i) {
            if (types_[i].name == name) {
                matches.push_back(i);
                break;
            }
        }
        if (matches.empty()) {
            for (std::size_t i = 0; i < types_.size(); ++i) {
                const auto& groups = types_[i].groups;
                if (std::find(groups.begin(), groups.end(), name) != groups.end()) {
                    matches.push_back(i);
                }
            }
        }
        if (matches.empty()) {
            throw std::invalid_argument("unknown node type or group '" + std::string(name) +
                                        "' in content expression '" + std::string(expression_) + "'");
        }
        for (std::size_t index : matches) {
            if (inline_content_ && *inline_content_ != types_[index].is_inline) {
                invalid_expression(expression_, "mixed inline and block content");
            }
            inline_content_ = types_[index].is_inline;
        }
        return matches;
    }

    void push_operator(char op) {
        while (!operators_.empty() && operators_.back() != '(' &&
               (operators_.back() == '.' || op == '|')) {
            reduce();
        }
        operators_.push_back(op);
    }

    void reduce() {
        Expr expr {operators_.back() == '.' ? ExprKind::Sequence : ExprKind::Choice};
        operators_.pop_back();
        expr.right = values_.back();
        values_.pop_back();
        expr.left = values_.back();
        values_.back() = append(std::move(expr));
    }

    std::size_t number() {
        skip_space();
        if (position_ == expression_.size() || expression_[position_] < '0' || expression_[position_] > '9') {
            invalid_expression(expression_, "expected repetition count");
        }
        std::size_t result = 0;
        while (position_ != expression_.size() && expression_[position_] >= '0' && expression_[position_] <= '9') {
            // Counts beyond the whole budget cannot compile, so their spelling must not overflow size_t first.
            if (result <= kCompilationBudget) {
                result = std::min(kCompilationBudget + 1,
                                  result * 10 + static_cast<std::size_t>(expression_[position_] - '0'));
            }
            ++position_;
        }
        return result;
    }
};

struct NFAEdge {
    const std::vector<std::size_t>* types;
    std::size_t next;
    std::size_t priority;
};

struct NFAState {
    std::vector<std::size_t> epsilon;
    std::vector<NFAEdge> edges;
};

struct CompileTask {
    std::size_t expression;
    std::size_t from;
    std::size_t to;
};

std::vector<NFAState> compile_nfa(const std::vector<Expr>& expressions, std::optional<std::size_t> root,
                                 Budget& budget) {
    std::vector<NFAState> states;
    auto state = [&]() {
        budget.charge();
        states.emplace_back();
        return states.size() - 1;
    };
    state();
    state();
    std::vector<CompileTask> tasks;
    if (root) {
        tasks.push_back({*root, 0, 1});
    } else {
        states[0].epsilon.push_back(1);
    }
    // Repetitions duplicate fragments, so tasks must be expanded under the same budget as the resulting states.
    while (!tasks.empty()) {
        CompileTask task = tasks.back();
        tasks.pop_back();
        const Expr& expr = expressions[task.expression];
        if (expr.kind == ExprKind::Name) {
            states[task.from].edges.push_back({&expr.types, task.to, task.expression});
        } else if (expr.kind == ExprKind::Sequence) {
            std::size_t middle = state();
            tasks.push_back({expr.right, middle, task.to});
            tasks.push_back({expr.left, task.from, middle});
        } else if (expr.kind == ExprKind::Choice) {
            tasks.push_back({expr.right, task.from, task.to});
            tasks.push_back({expr.left, task.from, task.to});
        } else {
            std::size_t current = task.from;
            std::vector<CompileTask> repeated;
            for (std::size_t i = 0; i < expr.min; ++i) {
                std::size_t next = expr.max && *expr.max <= expr.min && i + 1 == expr.min ? task.to : state();
                repeated.push_back({expr.left, current, next});
                current = next;
            }
            if (!expr.max) {
                // A zero-minimum loop must not return to a shared choice or sequence entry.
                if (expr.min == 0) {
                    std::size_t loop = state();
                    states[current].epsilon.push_back(loop);
                    current = loop;
                }
                states[current].epsilon.push_back(task.to);
                repeated.push_back({expr.left, current, current});
            } else {
                for (std::size_t i = expr.min; i < *expr.max; ++i) {
                    std::size_t next = i + 1 == *expr.max ? task.to : state();
                    states[current].epsilon.push_back(next);
                    repeated.push_back({expr.left, current, next});
                    current = next;
                }
                if (current != task.to) {
                    states[current].epsilon.push_back(task.to);
                }
            }
            tasks.insert(tasks.end(), repeated.rbegin(), repeated.rend());
        }
    }
    return states;
}

std::vector<std::size_t> closure(const std::vector<NFAState>& nfa, std::vector<std::size_t> states) {
    std::vector<bool> seen(nfa.size());
    std::vector<std::size_t> result;
    while (!states.empty()) {
        std::size_t state = states.back();
        states.pop_back();
        if (seen[state]) {
            continue;
        }
        seen[state] = true;
        result.push_back(state);
        states.insert(states.end(), nfa[state].epsilon.begin(), nfa[state].epsilon.end());
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::vector<std::string> required_once_types(const std::vector<Expr>& expressions,
                                             std::optional<std::size_t> root,
                                             const std::vector<ContentType>& types) {
    struct Task {
        std::size_t expression;
        bool required;
    };
    std::vector<Task> tasks;
    if (root) {
        tasks.push_back({*root, true});
    }
    std::vector<std::size_t> occurrences(types.size());
    std::vector<bool> required(types.size());
    while (!tasks.empty()) {
        Task task = tasks.back();
        tasks.pop_back();
        const Expr& expr = expressions[task.expression];
        if (expr.kind == ExprKind::Name) {
            for (std::size_t type : expr.types) {
                ++occurrences[type];
                required[type] = task.required && expr.types.size() == 1;
            }
        } else if (expr.kind == ExprKind::Sequence) {
            tasks.push_back({expr.right, task.required});
            tasks.push_back({expr.left, task.required});
        } else if (expr.kind == ExprKind::Choice) {
            tasks.push_back({expr.right, false});
            tasks.push_back({expr.left, false});
        } else {
            tasks.push_back({expr.left, false});
        }
    }
    std::vector<std::string> names;
    for (std::size_t i = 0; i < types.size(); ++i) {
        if (occurrences[i] == 1 && required[i]) {
            names.push_back(types[i].name);
        }
    }
    return names;
}

}  // namespace

ContentDFA compile_content(std::string_view expression, const std::vector<ContentType>& types) {
    Budget budget;
    ExpressionParser parser(expression, types, budget);
    std::optional<std::size_t> root = parser.parse();
    std::vector<NFAState> nfa = compile_nfa(parser.expressions(), root, budget);
    ContentDFA result;
    result.inline_content = parser.inline_content();
    std::vector<bool> referenced(types.size());
    for (const Expr& expr : parser.expressions()) {
        if (expr.kind != ExprKind::Name) {
            continue;
        }
        for (std::size_t type : expr.types) {
            if (!referenced[type]) {
                result.referenced_types.push_back(types[type].name);
                referenced[type] = true;
            }
        }
    }
    result.required_once_types = required_once_types(parser.expressions(), root, types);
    std::vector<std::vector<std::size_t>> subsets;
    std::map<std::vector<std::size_t>, std::size_t> known;
    auto state = [&](std::vector<std::size_t> subset) {
        auto found = known.find(subset);
        if (found != known.end()) {
            return found->second;
        }
        budget.charge();
        std::size_t index = subsets.size();
        known.emplace(subset, index);
        bool accepting = std::binary_search(subset.begin(), subset.end(), 1);
        subsets.push_back(std::move(subset));
        result.states.push_back({{}, accepting});
        return index;
    };
    state(closure(nfa, {0}));
    for (std::size_t i = 0; i < subsets.size(); ++i) {
        std::vector<std::vector<std::size_t>> targets(types.size());
        std::vector<std::size_t> outgoing;
        std::vector<std::pair<std::size_t, std::size_t>> priorities(
            types.size(), {parser.expressions().size(), types.size()});
        for (std::size_t source : subsets[i]) {
            for (const NFAEdge& edge : nfa[source].edges) {
                for (std::size_t j = 0; j < edge.types->size(); ++j) {
                    std::size_t type = (*edge.types)[j];
                    if (targets[type].empty()) {
                        outgoing.push_back(type);
                    }
                    priorities[type] = std::min(priorities[type], std::make_pair(edge.priority, j));
                    targets[type].push_back(edge.next);
                }
            }
        }
        // DFA subsets discard syntax order, which must still decide between possible fills.
        std::sort(outgoing.begin(), outgoing.end(), [&](std::size_t left, std::size_t right) {
            return priorities[left] < priorities[right];
        });
        std::vector<ContentDFA::Transition> transitions;
        for (std::size_t type : outgoing) {
            std::size_t next = state(closure(nfa, std::move(targets[type])));
            transitions.push_back({types[type].name, next});
        }
        result.states[i].transitions = std::move(transitions);
    }
    return result;
}

bool ContentDFA::match(const std::vector<std::string_view>& children) const {
    std::size_t state = 0;
    for (std::string_view child : children) {
        const auto& transitions = states[state].transitions;
        auto found = std::find_if(transitions.begin(), transitions.end(), [&](const Transition& transition) {
            return transition.type == child;
        });
        if (found == transitions.end()) {
            return false;
        }
        state = found->next;
    }
    return states[state].accepting;
}

bool ContentDFA::idempotent(std::string_view type) const {
    for (const State& state : states) {
        for (const Transition& transition : state.transitions) {
            if (transition.type != type) {
                continue;
            }
            const auto& target = states[transition.next].transitions;
            auto repeated = std::find_if(target.begin(), target.end(), [&](const Transition& next) {
                return next.type == type;
            });
            if (repeated == target.end() || repeated->next != transition.next) {
                return false;
            }
        }
    }
    return true;
}

bool ContentDFA::accepts_type(std::string_view type) const {
    return std::any_of(states.begin(), states.end(), [&](const State& state) {
        return std::any_of(state.transitions.begin(), state.transitions.end(), [&](const Transition& transition) {
            return transition.type == type;
        });
    });
}

bool ContentDFA::required_once(std::string_view type) const {
    return std::find(required_once_types.begin(), required_once_types.end(), type) != required_once_types.end();
}

std::optional<std::vector<ContentFill>> ContentDFA::fill(const std::vector<std::string_view>& children,
                                                         const std::vector<std::string>& creatable) const {
    struct Frame {
        std::size_t state;
        std::size_t position;
        std::size_t next = 0;
        bool original_tried = false;
    };
    std::unordered_set<std::string_view> allowed(creatable.begin(), creatable.end());
    // A creatable repetition must not keep inserting forever when the next original child cannot fit.
    std::set<std::pair<std::size_t, std::size_t>> seen;
    seen.insert({0, 0});
    std::vector<Frame> frames {{0, 0}};
    std::vector<ContentFill> filled;
    while (!frames.empty()) {
        Frame& frame = frames.back();
        const State& state = states[frame.state];
        if (frame.position == children.size() && state.accepting) {
            return filled;
        }
        if (!frame.original_tried) {
            frame.original_tried = true;
            if (frame.position < children.size()) {
                std::string_view type = children[frame.position];
                auto transition = std::find_if(state.transitions.begin(), state.transitions.end(),
                                                [&](const Transition& candidate) { return candidate.type == type; });
                if (transition != state.transitions.end() &&
                    seen.insert({transition->next, frame.position + 1}).second) {
                    filled.push_back({std::string(type), frame.position});
                    frames.push_back({transition->next, frame.position + 1});
                    continue;
                }
            }
        }
        bool descended = false;
        while (frame.next < state.transitions.size()) {
            const Transition& transition = state.transitions[frame.next++];
            if (allowed.find(transition.type) == allowed.end() ||
                !seen.insert({transition.next, frame.position}).second) {
                continue;
            }
            filled.push_back({transition.type, std::nullopt});
            frames.push_back({transition.next, frame.position});
            descended = true;
            break;
        }
        if (descended) {
            continue;
        }
        frames.pop_back();
        if (!frames.empty()) {
            filled.pop_back();
        }
    }
    return std::nullopt;
}

}  // namespace marktip
