#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include "AsstCaller.h"
#include "Config/TaskData.h"
#include "Vision/Config/OCRerConfig.h"
using J=nlohmann::json;
class Contract:public asst::OCRerConfig {
 public:const Params& params()const{return m_params;} asst::Rect roi;
 protected:void _set_roi(const asst::Rect& r)override{roi=r;}
};
int main(int argc,char** argv)try{
 if(argc!=5)throw std::runtime_error("usage: contract RELEASE CLIENT tasks.json OUT.json");
 std::filesystem::path root(argv[1]),out(argv[4]);AsstSetUserDir(out.parent_path().c_str());
 if(!AsstLoadResource(root.c_str()))throw std::runtime_error("base resource load failed");
 std::string client(argv[2]);if(client!="Official"&&!AsstLoadResource((root/"resource/global"/client).c_str()))throw std::runtime_error("client resource load failed");
 std::ifstream f(argv[3]);J names;f>>names;J rows=J::array();int non_ocr=0;J unresolved=J::array();
 for(auto& item:names){auto name=item.get<std::string>();auto task=asst::TaskData::get_instance().get(name);if(!task){unresolved.push_back(name);continue;}auto ocr=std::dynamic_pointer_cast<asst::OcrTaskInfo>(task);if(!ocr){++non_ocr;continue;}Contract config;config.set_task_info(ocr);auto& p=config.params();auto r=config.roi;
 rows.push_back({{"name",name},{"char_model",p.use_char_model},{"without_det",p.without_det},{"use_raw",p.use_raw},{"roi",{r.x,r.y,r.width,r.height}},{"bin_threshold",{p.bin_threshold_lower,p.bin_threshold_upper}},{"bin_expansion",p.bin_expansion},{"bin_trim",{p.bin_left_trim_threshold,p.bin_right_trim_threshold}},{"replace",p.replace},{"replace_full",p.replace_full},{"required",p.required},{"full_match",p.full_match}});
 }
 std::ofstream(out)<<J{{"client",client},{"ocr_tasks",rows},{"non_ocr_count",non_ocr},{"unresolved",unresolved}}.dump(2)<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
