"""
نموذج Temporal Fusion Transformer (TFT) للتنبؤ بأسعار الأراضي
================================================================
Smart Land Management Copilot — TFT Prediction Model
=====================================================

هندسة النموذج:
  1. Variable Selection Networks (VSN) — اختيار المتغيرات ديناميكياً
  2. Sequence-to-Sequence LSTM Encoder-Decoder — ترميز السلاسل الزمنية
  3. Multi-Head Temporal Self-Attention — الانتباه الزمني متعدد الرؤوس
  4. Gated Residual Networks (GRN) — الشبكات المتبقية المبوّبة
  5. Quantile Output — مخرجات التوزيع الكمي (P10, P50, P90)

التركيب: pip install torch numpy
التشغيل: python -c "from ai.tft_model import create_tft_model; m=create_tft_model(20,1); print(m)"
"""

import math
import logging
from typing import Optional, Dict, List, Tuple, Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# وحدات أساسية
# ════════════════════════════════════════════════════════════════

class GatedResidualNetwork(nn.Module):
    """
    شبكة متبقية موبوّبة (GRN)
    ──────────────────────────
    تُستخدم في كل طبقة من TFT لتحسين تدفق التدرجات.

    المعادلة:
        η₁ = ELU(W₁ · x + W₂ · c + b₁)
        η₂ = W₃ · η₁ + b₂
        output = LayerNorm(x + σ(W₄ · η₂) ⊙ η₂)

    حيث:
        x  : المدخل الرئيسي
        c  : السياق الاختياري (context)
        σ  : دالة Sigmoid
        ⊙  : ضرب عنصري (element-wise)
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: Optional[int] = None,
        dropout: float = 0.1,
        context_size: Optional[int] = None,
    ):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size or input_size
        self.context_size = context_size

        # الطبقة الخطية المشتركة للمدخل والسياق
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(
            context_size if context_size else input_size,
            hidden_size,
        )
        self.fc3 = nn.Linear(hidden_size, hidden_size)
        self.fc4 = nn.Linear(hidden_size, self.output_size)

        # إسقاط المدخل إذا اختلف حجمه عن المخرجات (للاتصال المتبقي)
        self.residual_proj = None
        if input_size != self.output_size:
            self.residual_proj = nn.Linear(input_size, self.output_size, bias=False)

        # طبقة التحويل القياسي (Layer Normalization)
        self.layer_norm = nn.LayerNorm(self.output_size)

        # تنشيطات
        self.elu = nn.ELU()
        self.sigmoid = nn.Sigmoid()
        self.dropout = nn.Dropout(dropout)

        # تهيئة الأوزان
        self._init_weights()

    def _init_weights(self):
        """تهيئة أوزان Xavier/Glorot للطبقات الخطية."""
        for module in [self.fc1, self.fc2, self.fc3, self.fc4]:
            nn.init.xavier_uniform_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(
        self,
        x: "torch.Tensor",
        context: Optional["torch.Tensor"] = None,
    ) -> "torch.Tensor":
        """
        التمرير الأمامي.

        المعاملات:
            x       : (batch, seq, input_size) أو (batch, input_size)
            context : (batch, context_size) — سياق اختياري

        المخرجات:
            (batch, seq, output_size) أو (batch, output_size)
        """
        # حفظ المدخل للاتصال المتبقي (skip connection)
        residual = x

        # η₁ = ELU(W₁ · x + W₂ · c + b₁)
        hidden = self.elu(self.fc1(x))
        if context is not None:
            # توسيع السياق إذا لزم الأمر: (batch, 1, context_size)
            if context.dim() == 2 and x.dim() == 3:
                context = context.unsqueeze(1).expand(-1, x.size(1), -1)
            hidden = hidden + self.fc2(context)

        # η₂ = W₃ · η₁ + b₂
        hidden = self.elu(self.fc3(hidden))
        hidden = self.dropout(hidden)

        # البوابة: σ(W₄ · η₂)
        gate = self.sigmoid(self.fc4(hidden))

        # الاتصال المتبقي مع البوابة
        if self.residual_proj is not None:
            residual = self.residual_proj(residual)

        return self.layer_norm(residual + gate * self.fc4(hidden))


class VariableSelectionNetwork(nn.Module):
    """
    شبكة اختيار المتغيرات (VSN)
    ────────────────────────────
    تختار ديناميكياً أي المتغيرات أكثر أهمية لكل خطوة زمنية.

    لكل متغير k:
        weight_k = Softmax(GRN(concat(all_inputs))_k)
        selected_k = GRN(input_k)

    المخرج = Σ (weight_k × selected_k)
    """

    def __init__(
        self,
        input_sizes: Dict[str, int],
        hidden_size: int,
        dropout: float = 0.1,
        context_size: Optional[int] = None,
    ):
        super().__init__()

        self.variable_names = list(input_sizes.keys())
        self.num_variables = len(self.variable_names)
        self.hidden_size = hidden_size

        total_input = sum(input_sizes.values())

        # GRN لكل متغير منفصل
        self.variable_grns = nn.ModuleDict({
            name: GatedResidualNetwork(
                input_size=size,
                hidden_size=hidden_size,
                output_size=hidden_size,
                dropout=dropout,
            )
            for name, size in input_sizes.items()
        })

        # GRN لحساب أوزان الاختيار
        self.selection_grn = GatedResidualNetwork(
            input_size=total_input,
            hidden_size=hidden_size,
            output_size=self.num_variables,
            dropout=dropout,
            context_size=context_size,
        )

        self.softmax = nn.Softmax(dim=-1)

    def forward(
        self,
        inputs: Dict[str, "torch.Tensor"],
        context: Optional["torch.Tensor"] = None,
    ) -> Tuple["torch.Tensor", Dict[str, "torch.Tensor"]]:
        """
        المعاملات:
            inputs  : dict {name: (batch, seq, size)}
            context : (batch, context_size) اختياري

        المخرجات:
            selected : (batch, seq, hidden_size)
            weights  : dict {name: (batch, seq, 1)} — أوزان كل متغير
        """
        # حزم كل المدخلات في موتر واحد
        concatenated = torch.cat(
            [inputs[name] for name in self.variable_names], dim=-1
        )

        # حساب أوزان الاختيار
        selection_weights = self.softmax(self.selection_grn(concatenated, context))

        # تطبيق GRN على كل متغير وجمع بوزن الاختيار
        selected = torch.zeros(
            concatenated.size(0),
            concatenated.size(1),
            self.hidden_size,
            device=concatenated.device,
        )

        weights_dict = {}
        for i, name in enumerate(self.variable_names):
            var_output = self.variable_grns[name](inputs[name])
            weight = selection_weights[..., i:i + 1]
            selected = selected + weight * var_output
            weights_dict[name] = weight

        return selected, weights_dict


class TemporalSelfAttention(nn.Module):
    """
    الانتباه الذاتي الزمني متعدد الرؤوس
    ──────────────────────────────────────
    يلتقط الاعتمادات طويلة المدى عبر التسلسل.

    سؤال (Q) من فك التشفير
    مفتاح (K) وقيمة (V) من مخرجات التشفير
    """

    def __init__(
        self,
        hidden_size: int,
        num_heads: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()

        assert hidden_size % num_heads == 0, (
            f"حجم المخفي {hidden_size} غير قابل للقسمة على عدد الرؤوس {num_heads}"
        )

        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads

        # طبقات الإسقاط لـ Query, Key, Value
        self.query_proj = nn.Linear(hidden_size, hidden_size)
        self.key_proj = nn.Linear(hidden_size, hidden_size)
        self.value_proj = nn.Linear(hidden_size, hidden_size)

        # إسقاط المخرجات
        self.out_proj = nn.Linear(hidden_size, hidden_size)

        # Dropout للانتباه
        self.attn_dropout = nn.Dropout(dropout)
        self.out_dropout = nn.Dropout(dropout)

        # تحيز الموضع النسبي — لكل رأس بشكل منفصل
        # الشكل: (num_heads, 2 * max_seq_len - 1)
        # يُستخدم كـ additive bias على درجات الانتباه
        self._max_seq = 256
        self.relative_attention_bias = nn.Parameter(
            torch.zeros(self.num_heads, 2 * self._max_seq - 1)
        )
        nn.init.trunc_normal_(self.relative_attention_bias, std=0.02)

    def _compute_relative_bias(
        self, target_len: int, source_len: int
    ) -> torch.Tensor:
        """
        حساب تحيز الانتباه النسبي.

        المخرجات: (num_heads, target_len, source_len)
        """
        # مسافة نسبية لكل زوج (target_pos, source_pos)
        range_vec = torch.arange(
            max(target_len, source_len),
            device=self.relative_attention_bias.device,
        )
        rel_pos = range_vec[None, :] - range_vec[:, None]  # (max_seq, max_seq)
        # تحويل إلى مؤشرات موجبة
        rel_pos = rel_pos + self._max_seq - 1
        rel_pos = torch.clamp(rel_pos, 0, 2 * self._max_seq - 2)

        # قص ليلائم الأبعاد المطلوبة
        rel_pos = rel_pos[:target_len, :source_len]  # (target, source)

        # فهرسة: (num_heads, 2*max-1) → (num_heads, target, source)
        bias = self.relative_attention_bias[:, rel_pos]
        return bias

    def forward(
        self,
        query: "torch.Tensor",
        key: "torch.Tensor",
        value: "torch.Tensor",
        mask: Optional["torch.Tensor"] = None,
    ) -> "torch.Tensor":
        """
        المعاملات:
            query : (batch, target_seq, hidden_size)
            key   : (batch, source_seq, hidden_size)
            value : (batch, source_seq, hidden_size)
            mask  : (batch, 1, 1, source_seq) — قناع اختياري

        المخرجات:
            (batch, target_seq, hidden_size)
        """
        batch_size = query.size(0)
        target_len = query.size(1)
        source_len = key.size(1)

        # إسقاط وتقسيم الرؤوس
        # (batch, seq, hidden) → (batch, heads, seq, head_dim)
        Q = self.query_proj(query).view(
            batch_size, target_len, self.num_heads, self.head_dim
        ).transpose(1, 2)

        K = self.key_proj(key).view(
            batch_size, source_len, self.num_heads, self.head_dim
        ).transpose(1, 2)

        V = self.value_proj(value).view(
            batch_size, source_len, self.num_heads, self.head_dim
        ).transpose(1, 2)

        # انتباه القياس بالنقاط
        # (batch, heads, target, head_dim) × (batch, heads, head_dim, source)
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.head_dim)

        # إضافة تحيز الموضع النسبي (additive bias per head)
        rel_bias = self._compute_relative_bias(target_len, source_len)
        scores = scores + rel_bias.unsqueeze(0)  # (1, heads, target, source)

        # تطبيق القناع
        if mask is not None:
            scores = scores.masked_fill(mask == 0, float("-inf"))

        # Softmax للاحتمالات
        attn_weights = F.softmax(scores, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)

        # تجميع القيم
        # (batch, heads, target, head_dim)
        context = torch.matmul(attn_weights, V)

        # دمج الرؤوس
        context = context.transpose(1, 2).contiguous().view(
            batch_size, target_len, self.hidden_size
        )

        return self.out_dropout(self.out_proj(context))


# ════════════════════════════════════════════════════════════════
# نموذج TFT الكامل
# ════════════════════════════════════════════════════════════════

class TemporalFusionTransformer(nn.Module):
    """
    نموذج Temporal Fusion Transformer (TFT) الكامل
    ─────────────────────────────────────────────────
    تصميم مُحسَّن للتنبؤ بالأسعار العقارية في السوق المصري.

    المكونات:
        1. VariableSelectionNetwork للمدخلات السابقة (encoder_inputs)
        2. VariableSelectionNetwork للمدخلات المستقبلية المعروفة (decoder_inputs)
        3. LSTM Encoder (2 طبقات)
        4. LSTM Decoder (2 طبقات)
        5. Multi-Head Temporal Self-Attention
        6. Gated Residual Network نهائي
        7. Quantile Output Layer (P10, P50, P90)

    المتغيرات المدعومة:
        - متغيرات فئوية ثابتة (static_categorical): المحافظة، نوع النشاط
        - متغيرات رقمية ثابتة (static_continuous): المساحة، عدد المرافق
        - متغيرات زمنية معروفة مستقبلية (known_future): الشهر، الموسم
        - متغيرات زمنية غير معروفة (observed): السعر، الحجم
    """

    def __init__(
        self,
        input_dim: int,
        output_dim: int = 1,
        hidden_size: int = 64,
        lstm_layers: int = 2,
        num_heads: int = 4,
        dropout: float = 0.2,
        quantiles: Optional[List[float]] = None,
        static_categorical_sizes: Optional[Dict[str, int]] = None,
        static_continuous_dim: int = 4,
        known_future_dim: int = 2,
        observed_dim: int = 1,
        encoder_length: int = 24,
        decoder_length: int = 12,
    ):
        """
        المعاملات:
            input_dim              : بُعد المدخل الكلي
            output_dim             : بُعد المخرج (عدد الأهداف التنبؤية)
            hidden_size            : حجم الطبقة المخفية (افتراضي: 64)
            lstm_layers            : عدد طبقات LSTM (افتراضي: 2)
            num_heads              : عدد رؤوس الانتباه (افتراضي: 4)
            dropout                : معدل الإسقاط (افتراضي: 0.2)
            quantiles              : الكميات للتنبؤ (افتراضي: [0.1, 0.5, 0.9])
            static_categorical_sizes : أعداد الفئات لكل متغير فئوي ثابت
            static_continuous_dim  : بُعد المتغيرات الرقمية الثابتة
            known_future_dim       : بُعد المتغيرات المستقبلية المعروفة
            observed_dim           : بُعد المتغيرات المُلاحظة
            encoder_length         : طول نافذة الإدخال (خطوات زمنية)
            decoder_length         : طول نافذة التنبؤ (خطوات زمنية)
        """
        super().__init__()


        self.input_dim = input_dim
        self.output_dim = output_dim
        self.hidden_size = hidden_size
        self.lstm_layers = lstm_layers
        self.num_heads = num_heads
        self.dropout_rate = dropout
        self.encoder_length = encoder_length
        self.decoder_length = decoder_length
        self.observed_dim = observed_dim
        self.known_future_dim = known_future_dim
        self.static_continuous_dim = static_continuous_dim

        self.quantiles = quantiles or [0.1, 0.5, 0.9]
        self.num_quantiles = len(self.quantiles)

        # ── تضمين المتغيرات الفئوية الثابتة ──
        self.static_categorical_sizes = static_categorical_sizes or {}
        self.static_categorical_embedders = nn.ModuleDict()
        total_categorical_embed = 0
        for name, num_categories in self.static_categorical_sizes.items():
            embed_dim = min(16, (num_categories + 1) // 2)
            self.static_categorical_embedders[name] = nn.Embedding(
                num_categories + 1, embed_dim, padding_idx=0
            )
            total_categorical_embed += embed_dim

        static_input_size = total_categorical_embed + static_continuous_dim

        # ── شبكة اختيار المتغيرات الثابتة ──
        # تحوّل المتغيرات الثابتة إلى سياق يُستخدم عبر كل الطبقات
        self.static_variable_selection = GatedResidualNetwork(
            input_size=static_input_size,
            hidden_size=hidden_size,
            output_size=hidden_size,
            dropout=dropout,
        )

        # ── سياق شبكة التشفير (c_s) ──
        # يُستخدم كسياق لـ VSN و LSTM encoder
        self.static_context_encoder = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            torch.nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
        )

        # ── سياق شبكة فك التشفير (c_h, c_c) ──
        # يُستخدم لتهيئة حالة LSTM decoder
        self.static_context_decoder_h = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            torch.nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
        )
        self.static_context_decoder_c = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            torch.nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
        )

        # ── سياق التنبؤ النهائي ──
        self.static_context_enrichment = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            torch.nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
        )

        # ── شبكة اختيار المتغيرات لتشفير السلاسل الزمنية ──
        encoder_vsn_input_sizes = {
            "observed_encoder": observed_dim,
            "known_future_encoder": known_future_dim,
        }
        self.encoder_variable_selection = VariableSelectionNetwork(
            input_sizes=encoder_vsn_input_sizes,
            hidden_size=hidden_size,
            dropout=dropout,
            context_size=hidden_size,  # سياق من المتغيرات الثابتة
        )

        # ── شبكة اختيار المتغيرات لفك تشفير السلاسل الزمنية ──
        decoder_vsn_input_sizes = {
            "observed_decoder": observed_dim,
            "known_future_decoder": known_future_dim,
        }
        self.decoder_variable_selection = VariableSelectionNetwork(
            input_sizes=decoder_vsn_input_sizes,
            hidden_size=hidden_size,
            dropout=dropout,
            context_size=hidden_size,
        )

        # ── LSTM Encoder ──
        self.encoder_lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=lstm_layers,
            batch_first=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )

        # ── LSTM Decoder ──
        self.decoder_lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=lstm_layers,
            batch_first=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )

        # ── Gated Skip Connection بعد LSTM ──
        self.post_lstm_gate_encoder = nn.Linear(
            hidden_size, hidden_size
        )
        self.post_lstm_gate_norm_encoder = nn.LayerNorm(hidden_size)

        self.post_lstm_gate_decoder = nn.Linear(
            hidden_size, hidden_size
        )
        self.post_lstm_gate_norm_decoder = nn.LayerNorm(hidden_size)

        # ── Multi-Head Temporal Self-Attention ──
        self.temporal_attention = TemporalSelfAttention(
            hidden_size=hidden_size,
            num_heads=num_heads,
            dropout=dropout,
        )

        # ── Gated Skip Connection بعد الانتباه ──
        self.post_attn_gate = nn.Linear(hidden_size, hidden_size)
        self.post_attn_norm = nn.LayerNorm(hidden_size)

        # ── Enrichment GRN ──
        self.enrichment_grn = GatedResidualNetwork(
            input_size=hidden_size,
            hidden_size=hidden_size,
            output_size=hidden_size,
            dropout=dropout,
            context_size=hidden_size,
        )

        # ── GRN نهائي قبل طبقة المخرجات ──
        self.final_gated_residual = GatedResidualNetwork(
            input_size=hidden_size,
            hidden_size=hidden_size,
            output_size=hidden_size,
            dropout=dropout,
        )

        # ── طبقة المخرجات الكمية ──
        # لكل كمية (quantile)، طبقة إسقاط منفصلة
        self.output_layers = nn.ModuleList([
            nn.Sequential(
                nn.Linear(hidden_size, hidden_size // 2),
                torch.nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_size // 2, output_dim),
            )
            for _ in range(self.num_quantiles)
        ])

        # تهيئة الأوزان
        self._init_weights()

    def _init_weights(self):
        """تهيئة أوزان النموذج."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.LSTM):
                for name, param in module.named_parameters():
                    if "weight_ih" in name:
                        nn.init.xavier_uniform_(param)
                    elif "weight_hh" in name:
                        nn.init.orthogonal_(param)
                    elif "bias" in name:
                        nn.init.zeros_(param)

    def _embed_static_variables(
        self,
        static_categorical: Optional[Dict[str, "torch.Tensor"]] = None,
        static_continuous: Optional["torch.Tensor"] = None,
    ) -> "torch.Tensor":
        """
        تضمين المتغيرات الثابتة في موتر واحد.

        المعاملات:
            static_categorical : dict {name: (batch,)} — مؤشرات فئوية
            static_continuous  : (batch, continuous_dim) — قيم رقمية

        المخرجات:
            (batch, static_input_size)
        """
        embeddings = []
        if static_categorical:
            for name, tensor in static_categorical.items():
                if name in self.static_categorical_embedders:
                    embeddings.append(
                        self.static_categorical_embedders[name](tensor)
                    )

        if static_continuous is not None:
            embeddings.append(static_continuous)

        if not embeddings:
            batch_hint = 1
            if static_categorical:
                first_key = list(static_categorical.keys())[0]
                batch_hint = static_categorical[first_key].size(0)
            elif static_continuous is not None:
                batch_hint = static_continuous.size(0)
            return torch.zeros(batch_hint, 1, device=torch.device("cpu"))

        return torch.cat(embeddings, dim=-1)

    def _gated_skip_connection(
        self,
        x: "torch.Tensor",
        residual: "torch.Tensor",
        gate_layer: nn.Module,
        norm_layer: nn.LayerNorm,
    ) -> "torch.Tensor":
        """اتصال متبقي موبوّب."""
        gate = torch.sigmoid(gate_layer(x))
        return norm_layer(residual + gate * x)

    def forward(
        self,
        observed_encoder: "torch.Tensor",
        known_future_encoder: "torch.Tensor",
        observed_decoder: "torch.Tensor",
        known_future_decoder: "torch.Tensor",
        static_categorical: Optional[Dict[str, "torch.Tensor"]] = None,
        static_continuous: Optional["torch.Tensor"] = None,
        encoder_mask: Optional["torch.Tensor"] = None,
    ) -> Dict[str, "torch.Tensor"]:
        """
        التمرير الأمامي الكامل لنموذج TFT.

        المعاملات:
            observed_encoder    : (batch, encoder_length, observed_dim)
                                  المتغيرات المُلاحظة في نافذة الإدخال
            known_future_encoder: (batch, encoder_length, known_future_dim)
                                  المتغيرات المستقبلية المعروفة في نافذة الإدخال
            observed_decoder    : (batch, decoder_length, observed_dim)
                                  المتغيرات المُلاحظة في نافذة التنبؤ
                                  (الأجزاء الماضية فقط — الباقي أصفار)
            known_future_decoder: (batch, decoder_length, known_future_dim)
                                  المتغيرات المستقبلية المعروفة في نافذة التنبؤ
            static_categorical  : dict {name: (batch,)} اختياري
            static_continuous   : (batch, continuous_dim) اختياري
            encoder_mask        : (batch, encoder_length) قناع اختياري

        المخرجات:
            dict {
                "predictions": (batch, decoder_length, num_quantiles, output_dim),
                "quantiles": list[float],
                "attention_weights": (batch, num_heads, decoder_length, encoder_length+decoder_length),
                "encoder_selection_weights": dict {name: (batch, encoder_length, 1)},
                "decoder_selection_weights": dict {name: (batch, decoder_length, 1)},
            }
        """
        # ── الخطوة 1: تضمين المتغيرات الثابتة ──
        static_embedding = self._embed_static_variables(
            static_categorical, static_continuous
        )

        # ── الخطوة 2: اختيار المتغيرات الثابتة ──
        static_context = self.static_variable_selection(static_embedding)

        # ── الخطوة 3: حساب سياقات الاشتقاق ──
        c_s = self.static_context_encoder(static_context)      # سياق التشفير
        c_h = self.static_context_decoder_h(static_context)    # حالة مخفية decoder
        c_c = self.static_context_decoder_c(static_context)    # حالة خلية decoder
        c_e = self.static_context_enrichment(static_context)   # سياق الإثراء

        # ── الخطوة 4: اختيار متغيرات المشفر (Encoder VSN) ──
        encoder_inputs = {
            "observed_encoder": observed_encoder,
            "known_future_encoder": known_future_encoder,
        }
        encoder_selected, encoder_weights = self.encoder_variable_selection(
            encoder_inputs, context=c_s
        )

        # ── الخطوة 5: LSTM Encoder ──
        encoder_lstm_out, _ = self.encoder_lstm(encoder_selected)

        # اتصال متبقي موبوّب بعد LSTM
        encoder_output = self._gated_skip_connection(
            encoder_lstm_out,
            encoder_selected,
            self.post_lstm_gate_encoder,
            self.post_lstm_gate_norm_encoder,
        )

        # ── الخطوة 6: اختيار متغيرات فك التشفير (Decoder VSN) ──
        decoder_inputs = {
            "observed_decoder": observed_decoder,
            "known_future_decoder": known_future_decoder,
        }
        decoder_selected, decoder_weights = self.decoder_variable_selection(
            decoder_inputs, context=c_s
        )

        # ── الخطوة 7: LSTM Decoder ──
        # تحويل حالة التهيئة
        c_h_expanded = c_h.unsqueeze(0).repeat(self.lstm_layers, 1, 1)
        c_c_expanded = c_c.unsqueeze(0).repeat(self.lstm_layers, 1, 1)

        decoder_lstm_out, _ = self.decoder_lstm(
            decoder_selected, (c_h_expanded, c_c_expanded)
        )

        # اتصال متبقي موبوّب بعد LSTM
        decoder_output = self._gated_skip_connection(
            decoder_lstm_out,
            decoder_selected,
            self.post_lstm_gate_decoder,
            self.post_lstm_gate_norm_decoder,
        )

        # ── الخطوة 8: الانتباه الذاتي الزمني ──
        # دمج مخرجات التشفير وفك التشفير
        combined = torch.cat([encoder_output, decoder_output], dim=1)

        attention_out = self.temporal_attention(
            query=decoder_output,
            key=combined,
            value=combined,
        )

        # اتصال متبقي موبوّب بعد الانتباه
        attention_output = self._gated_skip_connection(
            attention_out,
            decoder_output,
            self.post_attn_gate,
            self.post_attn_norm,
        )

        # ── الخطوة 9: Enrichment GRN ──
        enriched = self.enrichment_grn(attention_output, context=c_e)

        # ── الخطوة 10: GRN نهائي ──
        final = self.final_gated_residual(enriched)

        # ── الخطوة 11: طبقة المخرجات الكمية ──
        # لكل كمية، حساب التنبؤ بشكل منفصل
        predictions = []
        for i, output_layer in enumerate(self.output_layers):
            pred = output_layer(final)  # (batch, decoder_length, output_dim)
            predictions.append(pred)

        # تجميع الكميات: (batch, decoder_length, num_quantiles, output_dim)
        predictions = torch.stack(predictions, dim=2)

        return {
            "predictions": predictions,
            "quantiles": self.quantiles,
            "attention_weights": None,  # يمكن حسابها من TemporalSelfAttention
            "encoder_selection_weights": encoder_weights,
            "decoder_selection_weights": decoder_weights,
        }

    def predict(
        self,
        observed_encoder: "torch.Tensor",
        known_future_encoder: "torch.Tensor",
        observed_decoder: "torch.Tensor",
        known_future_decoder: "torch.Tensor",
        static_categorical: Optional[Dict[str, "torch.Tensor"]] = None,
        static_continuous: Optional["torch.Tensor"] = None,
        quantile_idx: int = 1,
    ) -> "torch.Tensor":
        """
        تنبؤ مبسّط — يُرجع فقط الكمية المطلوبة (افتراضياً P50 = الوسيط).

        المعاملات:
            ... نفس forward()
            quantile_idx : مؤشر الكمية (0=P10, 1=P50, 2=P90)

        المخرجات:
            (batch, decoder_length, output_dim)
        """
        self.eval()
        with torch.no_grad():
            result = self.forward(
                observed_encoder=observed_encoder,
                known_future_encoder=known_future_encoder,
                observed_decoder=observed_decoder,
                known_future_decoder=known_future_decoder,
                static_categorical=static_categorical,
                static_continuous=static_continuous,
            )
            return result["predictions"][:, :, quantile_idx, :]


# ════════════════════════════════════════════════════════════════
# دالة المصنع — نقطة الدخول الرئيسية
# ════════════════════════════════════════════════════════════════

def create_tft_model(
    input_dim: int,
    output_dim: int = 1,
    hidden_size: int = 64,
    dropout: float = 0.2,
    num_heads: int = 4,
    lstm_layers: int = 2,
    quantiles: Optional[List[float]] = None,
    static_categorical_sizes: Optional[Dict[str, int]] = None,
    static_continuous_dim: int = 4,
    known_future_dim: int = 2,
    observed_dim: int = 1,
    encoder_length: int = 24,
    decoder_length: int = 12,
) -> TemporalFusionTransformer:
    """
    إنشاء نموذج TFT جاهز للتدريب.

    هذه هي الدالة الرئيسية التي يُنصح باستخدامها لإنشاء النموذج.

    المعاملات:
        input_dim    : بُعد المدخل الكلي (عدد الميزات في كل خطوة زمنية)
        output_dim   : بُعد المخرج (عدد الأهداف التنبؤية، افتراضي: 1)
        hidden_size  : حجم الطبقة المخفية (افتراضي: 64)
        dropout      : معدل الإسقاط (افتراضي: 0.2)
        num_heads    : عدد رؤوس الانتباه (افتراضي: 4)
        lstm_layers  : عدد طبقات LSTM (افتراضي: 2)
        quantiles    : الكميات للتنبؤ (افتراضي: [0.1, 0.5, 0.9])
        static_categorical_sizes : dict {اسم_المتغير: عدد_الفئات}
        static_continuous_dim  : بُعد المتغيرات الرقمية الثابتة
        known_future_dim       : بُعد المتغيرات المعروفة مستقبلاً
        observed_dim           : بُعد المتغيرات المُلاحظة
        encoder_length         : طول نافذة الإدخال (24 شهراً افتراضياً)
        decoder_length         : طول نافذة التنبؤ (12 شهراً افتراضياً)

    المخرجات:
        TemporalFusionTransformer — نموذج جاهز للتدريب

    مثال:
        >>> model = create_tft_model(input_dim=20, output_dim=1)
        >>> print(f"المعاملات: {sum(p.numel() for p in model.parameters()):,}")
        المعمار:
            Input → VSN → LSTM Encoder → LSTM Decoder
                  → Multi-Head Attention → GRN → Quantile Output
    """
    

    model = TemporalFusionTransformer(
        input_dim=input_dim,
        output_dim=output_dim,
        hidden_size=hidden_size,
        lstm_layers=lstm_layers,
        num_heads=num_heads,
        dropout=dropout,
        quantiles=quantiles,
        static_categorical_sizes=static_categorical_sizes,
        static_continuous_dim=static_continuous_dim,
        known_future_dim=known_future_dim,
        observed_dim=observed_dim,
        encoder_length=encoder_length,
        decoder_length=decoder_length,
    )

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    logger.info(
        f"تم إنشاء نموذج TFT: {total_params:,} معامل إجمالي, "
        f"{trainable_params:,} قابل للتدريب"
    )

    return model


# ════════════════════════════════════════════════════════════════
# دالة الخسارة الكمية (Quantile Loss)
# ════════════════════════════════════════════════════════════════

class QuantileLoss(nn.Module):
    """
    دالة خسارة الكميات (Pinball Loss)
    ───────────────────────────────────
    تُستخدم للتنبؤ بالفترات الموثوقة.

    لكل كمية τ:
        L_τ(y, ŷ) = max(τ(y - ŷ), (τ - 1)(y - ŷ))

    الميزة: تُعاقب التنبؤات بشكل مختلف حسب موقع الكمية:
        - τ = 0.1 (P10): تُعاقب التجاوز أكثر (optimistic bound)
        - τ = 0.5 (P50): خسارة مطلقة عادية (MAE)
        - τ = 0.9 (P90): تُعاقب التقدير الزائد أكثر (conservative bound)
    """

    def __init__(self, quantiles: List[float]):
        super().__init__()
        self.quantiles = quantiles
        self.register_buffer(
            "quantile_tensor",
            torch.tensor(quantiles, dtype=torch.float32),
        )

    def forward(
        self, predictions: "torch.Tensor", targets: "torch.Tensor"
    ) -> "torch.Tensor":
        """
        المعاملات:
            predictions : (batch, seq_len, num_quantiles, output_dim)
            targets     : (batch, seq_len, output_dim)

        المخرجات:
            scalar — متوسط الخسارة عبر جميع الكميات والأبعاد
        """
        # توسيع الأهداف لمطابقة أبعاد الكميات
        # (batch, seq, 1, output_dim) → بث تلقائي
        targets_expanded = targets.unsqueeze(2)

        # حساب الأخطاء
        errors = targets_expanded - predictions  # (batch, seq, num_q, out)

        # Pinball Loss
        quantile_losses = torch.where(
            errors >= 0,
            self.quantile_tensor.view(1, 1, -1, 1) * errors,
            (self.quantile_tensor.view(1, 1, -1, 1) - 1.0) * errors,
        )

        return quantile_losses.mean()


# ════════════════════════════════════════════════════════════════
# أدوات مساعدة
# ════════════════════════════════════════════════════════════════

def count_parameters(model: "nn.Module") -> Dict[str, int]:
    """
    عدّ المعاملات التفصيلي للنموذج.

    المخرجات:
        dict {
            "total": int,
            "trainable": int,
            "frozen": int,
            "by_layer": dict {layer_name: param_count},
        }
    """
    total = 0
    trainable = 0
    by_layer = {}

    for name, param in model.named_parameters():
        count = param.numel()
        total += count
        if param.requires_grad:
            trainable += count
        by_layer[name] = count

    return {
        "total": total,
        "trainable": trainable,
        "frozen": total - trainable,
        "by_layer": by_layer,
    }


def get_model_info(model: TemporalFusionTransformer) -> Dict[str, Any]:
    """
    معلومات تفصيلية عن النموذج — مفيدة للتسجيل والتوثيق.

    المخرجات:
        dict يحتوي على الأبعاد والمعاملات ومعلومات الهندسة
    """
    params = count_parameters(model)
    device = next(model.parameters()).device

    return {
        "model_class": model.__class__.__name__,
        "device": str(device),
        "hidden_size": model.hidden_size,
        "num_heads": model.num_heads,
        "lstm_layers": model.lstm_layers,
        "encoder_length": model.encoder_length,
        "decoder_length": model.decoder_length,
        "quantiles": model.quantiles,
        "num_quantiles": model.num_quantiles,
        "output_dim": model.output_dim,
        "dropout": model.dropout_rate,
        "total_parameters": params["total"],
        "trainable_parameters": params["trainable"],
        "frozen_parameters": params["frozen"],
        "model_size_mb": round(
            sum(p.numel() * p.element_size() for p in model.parameters()) / (1024 * 1024),
            2,
        ),
    }