
exports.login = async (req,res)=>{
    const {email} = req.params

    if(email==='abc'){
        res.send("you are logged in")
    }else{
        res.send("you are not logged in")
    }
}

