// Run the released OCRer postprocessing on explicit strings, without inference.
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <opencv2/opencv.hpp>
#include "AsstCaller.h"
#include "Vision/OCRer.h"
using J=nlohmann::json;
class RuleProbe: public asst::OCRer {
public:
    using asst::OCRer::OCRer;
    J inspect(const std::string& text) {
        asst::OcrPack::Result r; r.text=text; r.score=1;
        postproc_trim_(r); std::string trimmed=r.text;
        postproc_replace_(r); std::string replaced=r.text;
        bool accepted=filter_and_replace_by_required_(r);
        return {{"raw",text},{"trimmed",trimmed},{"replaced",replaced},{"final",r.text},{"accepted",accepted}};
    }
};
int main(int argc,char** argv) try {
    if(argc!=5) throw std::runtime_error("usage: rules RELEASE CLIENT INPUT OUTPUT");
    std::filesystem::path release(argv[1]), output(argv[4]);
    std::filesystem::create_directories(output.parent_path());
    AsstSetUserDir(output.parent_path().c_str());
    if(!AsstLoadResource(release.c_str())) throw std::runtime_error("resource load failed");
    std::string client(argv[2]);
    if(client!="Official" && !AsstLoadResource((release/"resource/global"/client).c_str())) throw std::runtime_error("client load failed");
    std::ifstream input(argv[3]);J rows;input>>rows;J out=J::array();
    cv::Mat im(48,320,CV_8UC3,cv::Scalar(0,0,0));
    for(const auto& row:rows){
        RuleProbe probe(im);probe.set_task_info(row.at("task").get<std::string>());
        if(row.contains("required"))probe.set_required(row["required"].get<std::vector<std::string>>());
        auto r=probe.inspect(row.at("raw").get<std::string>());r["task"]=row["task"];r["id"]=row["id"];out.push_back(r);
    }
    std::ofstream(output)<<out.dump(2)<<'\n';return 0;
} catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
