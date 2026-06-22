ATTACH TABLE _ UUID '8053f4e0-537c-4323-ad09-a7647cbaa020'
(
    `prv_name` String,
    `city_name` String,
    `admdvs_name` String COMMENT '行政区划名称',
    `psn_no` String COMMENT '参保人唯一编号',
    `psn_name` String COMMENT '参保人姓名',
    `certno` String COMMENT '身份证号码',
    `emp_no` String,
    `emp_name` String,
    `emp_type` String,
    `gend` String,
    `cert_gend` String,
    `age` Int64,
    `insutype` String,
    `med_type` String COMMENT '医疗类别 (门诊/住院/药店)',
    `psn_type` String,
    `insu_admdvs` String,
    `setl_id` String,
    `begndate` String,
    `enddate` String,
    `setl_time` String COMMENT '结算时间',
    `feelist_psn_no` String,
    `fee_ocur_time` String,
    `mdtrt_id` String,
    `fixmedins_code` String COMMENT '医药机构/医院编码',
    `fixmedins_name` String COMMENT '医药机构名称',
    `hilist_code` String,
    `hilist_name` String,
    `cnt` Float64,
    `pric` Float64,
    `det_item_fee_sumamt` Float64,
    `fx_level` String
)
ENGINE = MergeTree
ORDER BY tuple()
SETTINGS index_granularity = 8192
